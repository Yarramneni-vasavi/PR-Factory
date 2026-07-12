from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentBaseModel(BaseModel):
    class Config:
        extra = "forbid"


class RelevantFile(AgentBaseModel):
    path: str
    reason: str
    priority: Literal["high", "medium", "low"] = "medium"
    expected_change: str | None = None


class PlannerInput(AgentBaseModel):
    issue_url: str
    issue_title: str
    issue_body: str
    issue_comments: list[str] = Field(default_factory=list)
    signal_analysis: dict[str, Any]
    project_stack: dict[str, Any]
    candidate_files: list[dict[str, Any]] = Field(default_factory=list)
    vector_context: list[dict[str, Any]] = Field(default_factory=list)
    relevant_tests: list[str] = Field(default_factory=list)
    repo_path: str


class PlannerBrief(AgentBaseModel):
    issue_summary: str
    acceptance_criteria: list[str]
    relevant_files: list[RelevantFile]
    suspected_root_cause: str | None = None
    fix_strategy: str
    tests_to_run: list[str]
    risks: list[str] = Field(default_factory=list)
    decision_notes: list[str] = Field(default_factory=list)


class CoderInput(AgentBaseModel):
    repo_path: str
    planner_brief: PlannerBrief
    project_stack: dict[str, Any]
    candidate_files: list[dict[str, Any]] = Field(default_factory=list)
    vector_context: list[dict[str, Any]] = Field(default_factory=list)
    relevant_tests: list[str] = Field(default_factory=list)
    task_id: str | None = None
    task_title: str | None = None
    task_focus: dict[str, Any] | None = None


class FileChangePlan(AgentBaseModel):
    path: str
    action: Literal["inspect", "modify", "create", "delete", "test"]
    reason: str
    instructions: str


class CoderResult(AgentBaseModel):
    summary: str
    file_change_plan: list[FileChangePlan]
    commands_to_run: list[str]
    tests_to_run: list[str]
    success_criteria: list[str]
    applied: bool = False
    worker_output: str | None = None
    risks: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
