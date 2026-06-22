"""Constrained patrol-deployment optimiser.

Objective: maximise collected PRIORITY UTILITY per officer-hour, subject to travel time,
shift capacity, and coverage. Utility = bias-adjusted risk × CII, so we prioritise
predicted risk, not just where we already ticket. Modelled as team orienteering: each
unit starts at the zone depot, visits a subset of candidate segments within its shift.

We say "priority utility", NOT "preventable impact": this solver currently uses
straight-line (haversine) travel, a constant patrol speed, and a virtual zone-centroid
depot. Those are planning approximations. Field claims of prevented violations require
police-station depots, road-network travel times, and a measured pre/post study — none
are done here, so the output is a prioritisation score only.

Pure module: it takes candidate stops and returns routes. Fetching candidates and the
human-approval gate live in the application service. OR-Tools solves it; a greedy
nearest-neighbour heuristic is the dependency-free fallback if OR-Tools is unavailable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

METHOD_CAVEATS = (
    "Planning approximation: straight-line travel, constant speed, virtual centroid "
    "depot. 'Priority utility' is a prioritisation score, not measured prevented impact."
)


@dataclass(frozen=True)
class Stop:
    physical_id: str
    lat: float
    lon: float
    priority_utility: float  # bias-adjusted risk × CII, >= 0 (NOT preventable impact)


@dataclass(frozen=True)
class Route:
    unit: int
    stops: list[str]         # ordered physical_ids
    priority_utility: float
    minutes: float


@dataclass(frozen=True)
class DeploymentResult:
    routes: list[Route]
    total_priority_utility: float
    coverage_fraction: float
    solver: str
    method_caveats: str = METHOD_CAVEATS
    requires_human_approval: bool = True   # ParkIQ recommends; a human approves.


def _haversine_m(a: Stop, b: Stop) -> float:
    R = 6_371_000
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi = math.radians(b.lat - a.lat)
    dlmb = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _depot(stops: list[Stop]) -> Stop:
    return Stop("__depot__", sum(s.lat for s in stops) / len(stops),
                sum(s.lon for s in stops) / len(stops), 0.0)


def optimise_routes(
    stops: list[Stop],
    *,
    n_units: int,
    shift_minutes: int = 240,
    dwell_minutes: int = 12,
    speed_kmph: float = 18.0,
    solver_time_s: int = 5,
) -> DeploymentResult:
    if not stops or n_units < 1:
        return DeploymentResult([], 0.0, 0.0, "empty")
    try:
        return _solve_ortools(stops, n_units, shift_minutes, dwell_minutes, speed_kmph, solver_time_s)
    except Exception:
        return _solve_greedy(stops, n_units, shift_minutes, dwell_minutes, speed_kmph)


def _time_matrix(nodes: list[Stop], dwell_minutes: int, speed_kmph: float) -> list[list[int]]:
    mpm = speed_kmph * 1000 / 60  # metres per minute
    n = len(nodes)
    mat = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            travel = _haversine_m(nodes[i], nodes[j]) / mpm
            mat[i][j] = int(round(travel + (dwell_minutes if j != 0 else 0)))
    return mat


def _solve_ortools(stops, n_units, shift_minutes, dwell_minutes, speed_kmph, solver_time_s):
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    nodes = [_depot(stops)] + stops
    tmat = _time_matrix(nodes, dwell_minutes, speed_kmph)
    mgr = pywrapcp.RoutingIndexManager(len(nodes), n_units, 0)
    routing = pywrapcp.RoutingModel(mgr)

    cb = routing.RegisterTransitCallback(
        lambda i, j: tmat[mgr.IndexToNode(i)][mgr.IndexToNode(j)]
    )
    routing.SetArcCostEvaluatorOfAllVehicles(cb)
    routing.AddDimension(cb, 0, shift_minutes, True, "Time")

    # Drop is allowed; dropping a node costs its prize → solver collects utility.
    for node in range(1, len(nodes)):
        prize = max(1, int(nodes[node].priority_utility * 1000))
        routing.AddDisjunction([mgr.NodeToIndex(node)], prize)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(solver_time_s)
    sol = routing.SolveWithParameters(params)
    if sol is None:
        raise RuntimeError("no solution")

    routes, visited, total = [], set(), 0.0
    time_dim = routing.GetDimensionOrDie("Time")
    for v in range(n_units):
        idx = routing.Start(v)
        seq, util = [], 0.0
        while not routing.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            if node != 0:
                seq.append(nodes[node].physical_id)
                util += nodes[node].priority_utility
                visited.add(node)
            idx = sol.Value(routing.NextVar(idx))
        minutes = sol.Value(time_dim.CumulVar(routing.End(v)))
        if seq:
            routes.append(Route(v, seq, round(util, 4), float(minutes)))
        total += util
    return DeploymentResult(routes, round(total, 4), len(visited) / len(stops), "ortools")


def _solve_greedy(stops, n_units, shift_minutes, dwell_minutes, speed_kmph):
    """Round-robin nearest-neighbour by utility. Dependency-free fallback."""
    mpm = speed_kmph * 1000 / 60
    depot = _depot(stops)
    remaining = sorted(stops, key=lambda s: s.priority_utility, reverse=True)
    units = [{"pos": depot, "time": 0.0, "seq": [], "util": 0.0} for _ in range(n_units)]
    visited = set()
    progress = True
    while remaining and progress:
        progress = False
        for u in units:
            best, best_cost = None, None
            for s in remaining:
                cost = _haversine_m(u["pos"], s) / mpm + dwell_minutes
                if u["time"] + cost <= shift_minutes and (best is None or cost < best_cost):
                    best, best_cost = s, cost
            if best is not None:
                u["time"] += best_cost
                u["pos"] = best
                u["seq"].append(best.physical_id)
                u["util"] += best.priority_utility
                remaining.remove(best)
                visited.add(best.physical_id)
                progress = True
    routes = [
        Route(i, u["seq"], round(u["util"], 4), round(u["time"], 1))
        for i, u in enumerate(units) if u["seq"]
    ]
    total = sum(r.priority_utility for r in routes)
    return DeploymentResult(routes, round(total, 4), len(visited) / len(stops), "greedy")
