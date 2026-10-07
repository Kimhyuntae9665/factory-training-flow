"""Seeded synthetic line, implemented with SimPy discrete-event resources."""
import random
import statistics
import uuid

import simpy
import workforce

HORIZON = 480
SEEDS = list(range(10))
SCENARIOS = {
    "baseline": {"name": "기준 공정", "description": "수동 운반·조립, 검사 자격자 1명", "transport_min": 6, "assembly_min": 10, "qualified_workers": 1, "robot": False, "training": False},
    "robot": {"name": "AMR·로봇 대안", "description": "운반·조립 자동화, 검사 자격자 1명 유지", "transport_min": 2, "assembly_min": 5, "qualified_workers": 1, "robot": True, "training": False},
    "training": {"name": "교육 자원 대안", "description": "수동 공정 유지, 가상 사전교육으로 검사 자격자 2명", "transport_min": 6, "assembly_min": 10, "qualified_workers": 2, "robot": False, "training": True},
    "combined": {"name": "자동화·교육 결합", "description": "운반·조립 자동화와 검사 자격자 2명 결합", "transport_min": 2, "assembly_min": 5, "qualified_workers": 2, "robot": True, "training": True},
}


def job_schedule(seed, demand_multiplier):
    rng = random.Random(seed)
    jobs, arrival = [], 0.0
    while arrival < HORIZON:
        jobs.append({"id": f"J{len(jobs) + 1:03}", "arrival": arrival,
                     "transport_factor": rng.uniform(.85, 1.15), "assembly_factor": rng.uniform(.85, 1.15),
                     "inspection_factor": rng.uniform(.85, 1.15), "rework": rng.random() < .10})
        arrival += rng.uniform(6.4, 9.6) / demand_multiplier
    return jobs


def simulate(scenario_id, seed, demand_multiplier=1.0, workforce_state=None):
    hr = (workforce_state or workforce.load())["aggregate"]
    cfg = dict(SCENARIOS[scenario_id], qualified_workers=hr["qualified_after"] if SCENARIOS[scenario_id]["training"] else hr["qualified_before"])
    env = simpy.Environment()
    capacities = {"transport": 1, "assembly": 1, "inspection": cfg["qualified_workers"]}
    resources = {stage: simpy.Resource(env, capacity=cap) for stage, cap in capacities.items()}
    slots = {stage: list(range(1, cap + 1)) for stage, cap in capacities.items()}
    jobs = job_schedule(seed, demand_multiplier)
    timeline, trace, completions = [], [], []
    released = interventions = rework_visits = 0

    def visit(job, stage, duration, state):
        nonlocal interventions, rework_visits
        waiting_since = env.now
        with resources[stage].request() as req:
            yield req
            state["wait"] += env.now - waiting_since
            slot = slots[stage].pop(0)
            start = env.now
            end = min(start + duration, HORIZON)
            timeline.append({"job_id": job["id"], "stage": stage, "start": round(start, 4), "end": round(end, 4),
                             "resource_id": f"{stage}-{slot}", "completed_visit": start + duration < HORIZON})
            trace.append({"t": round(start, 4), "type": "start", "job_id": job["id"], "stage": stage, "note": "합성 자원 획득"})
            if stage == "inspection" or not cfg["robot"]:
                interventions += 1
            yield env.timeout(duration)
            slots[stage].append(slot)
            slots[stage].sort()

    def process(job):
        nonlocal released, rework_visits
        released += 1
        state = {"wait": 0.0}
        trace.append({"t": round(env.now, 4), "type": "released", "job_id": job["id"], "stage": "transport", "note": "합성 주문 투입"})
        yield from visit(job, "transport", cfg["transport_min"] * job["transport_factor"], state)
        yield from visit(job, "assembly", cfg["assembly_min"] * job["assembly_factor"], state)
        yield from visit(job, "inspection", 12 * job["inspection_factor"], state)
        if job["rework"]:
            rework_visits += 1
            trace.append({"t": round(env.now, 4), "type": "rework", "job_id": job["id"], "stage": "assembly", "note": "합성 10% 재작업 플래그"})
            yield from visit(job, "assembly", 4 * job["assembly_factor"], state)
            yield from visit(job, "inspection", 6 * job["inspection_factor"], state)
        completions.append({"job_id": job["id"], "t": env.now, "lead": env.now - job["arrival"], "wait": state["wait"]})
        trace.append({"t": round(env.now, 4), "type": "completed", "job_id": job["id"], "stage": "inspection", "note": "합성 완료"})

    def release():
        for job in jobs:
            yield env.timeout(job["arrival"] - env.now)
            env.process(process(job))

    env.process(release())
    env.run(until=HORIZON)
    occupied = {stage: sum(x["end"] - x["start"] for x in timeline if x["stage"] == stage) for stage in capacities}
    completed = len(completions)
    metrics = {"completed": completed, "throughput_per_hour": completed / 8,
               "mean_lead_time_min": statistics.mean(x["lead"] for x in completions) if completions else 0,
               "mean_wait_min": statistics.mean(x["wait"] for x in completions) if completions else 0,
               "wip_end": released - completed, "manual_interventions": interventions,
               "skill_coverage_pct": cfg["qualified_workers"] / hr["total_workers"] * 100,
               "training_hours": hr["total_training_hours"] if cfg["training"] else 0, "total_worker_hours": hr["total_workers"] * 8,
               "utilization": {stage: occupied[stage] / (HORIZON * cap) * 100 for stage, cap in capacities.items()},
               "released": released, "rework_started": rework_visits}
    return {"metrics": metrics, "timeline": timeline, "trace": trace[:120],
            "arrival_schedule": [round(x["arrival"], 4) for x in jobs],
            "arrivals": [{"job_id": x["id"], "arrival": round(x["arrival"], 4)} for x in jobs],
            "completion_times": {x["job_id"]: round(x["t"], 4) for x in completions}}


def compare(plan, experiment_id=None):
    workforce_state = workforce.load()
    hr = workforce_state["aggregate"]
    ids = ["baseline"] + [sid for sid in plan["selected_ids"] if sid != "baseline"]
    ids = list(dict.fromkeys(ids))
    demand = plan["interpretation"]["demand_multiplier"]
    scenarios = []
    for sid in ids:
        runs = [simulate(sid, seed, demand, workforce_state) for seed in SEEDS]
        summary, means = {}, {}
        for key in runs[0]["metrics"]:
            if key == "utilization":
                continue
            values = [run["metrics"][key] for run in runs]
            summary[key] = {"mean": round(statistics.mean(values), 4), "min": round(min(values), 4), "max": round(max(values), 4)}
            means[key] = summary[key]["mean"]
        means["utilization"] = {stage: round(statistics.mean(run["metrics"]["utilization"][stage] for run in runs), 4) for stage in ("assembly", "inspection", "transport")}
        summary["utilization"] = {stage: {"mean": means["utilization"][stage], "min": round(min(run["metrics"]["utilization"][stage] for run in runs), 4), "max": round(max(run["metrics"]["utilization"][stage] for run in runs), 4)} for stage in means["utilization"]}
        scenarios.append({"id": sid, "name": SCENARIOS[sid]["name"], "description": SCENARIOS[sid]["description"],
                          "config": dict(SCENARIOS[sid], qualified_workers=hr["qualified_after"] if SCENARIOS[sid]["training"] else hr["qualified_before"], total_workers=hr["total_workers"], inspection_min=12, demand_multiplier=demand),
                          "metrics": means, "summary": summary, "trace": runs[0]["trace"], "timeline": runs[0]["timeline"],
                          "arrivals": runs[0]["arrivals"], "completion_times": runs[0]["completion_times"]})
    best = max(scenarios, key=lambda x: (x["metrics"]["completed"], -x["metrics"]["mean_lead_time_min"]))
    return {"experiment_id": experiment_id or uuid.uuid4().hex, "plan": plan, "baseline_id": "baseline", "horizon_min": HORIZON,
            "seeds": SEEDS, "hr": hr, "assumptions": {"total_workers": hr["total_workers"], "qualified_before": hr["qualified_before"], "qualified_after_training": hr["qualified_after"],
                "inspection_min": 12, "rework_probability": .10, "rework_assembly_min": 4, "rework_inspection_min": 6,
                "arrival_interval_min": "Uniform(6.4,9.6) / demand_multiplier", "duration_factor": "Uniform(0.85,1.15)",
                "training": "가상 사전교육8시간 후 자격 취득을 가정. 교대 근무 인원4명 유지, 실제 교육 효과 주장 아님",
                "worker_hours": "4명 × 8시간 = 32 인시. 교육8시간은 사전교육 투입이며 교대 인시에 더하지 않음",
                "metric_scope": "완료·대기·리드타임은 480분 미만 완료 작업 기준; WIP는 종료시 미완료 주문. 개입은 시작된 수동 방문 수",
                "utilization": "시작된 방문의 horizon 내 점유시간 / (480분 × 자원 capacity) ×100",
                "aggregation": "동일한10개 seed·주문/재작업 플래그로 대안 비교; metrics는 seed 평균, timeline/trace는 seed0",
                "trace_limit": 120, "source_ids": ["SIM-01", "MODEL-01"]}, "scenarios": scenarios,
            "recommendation": {"scenario_id": best["id"], "reason": "비교한 대안 중 평균 완료 수 최대, 동률이면 완료 작업 리드타임 최소. 비용·안전·투자수익 최적화 아님.",
                "limitations": ["모든 시간과 인원은 합성 가정", "10seed 관찰 범위이며 통계적 효과·현장 실증이 아님", "미완료 작업의 대기는 평균 대기시간에 포함하지 않음", "실제 장비·HR 시스템·작업자와 연결하지 않음"]}, "synthetic": True}


def demo():
    plan = {"plan_id": "demo-baseline", "request": "수요 1.0배, 현재 운영과 로봇·교육 대안을 모두 비교합니다.", "mode": "rules", "model": None,
            "latency_ms": 0, "interpretation": {"demand_multiplier": 1.0, "allow_robot": True, "allow_training": True},
            "selected_ids": ["robot", "training", "combined"], "selected_focus_id": None, "rationale": ["명시적 규칙 기준 데모, LLM 미실행"],
            "raw_output": "", "warnings": ["합성 데이터·가상 자격 취득 가정"], "source_ids": ["SIM-01"]}
    return compare(plan, "demo-default")
