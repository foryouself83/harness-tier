# {{PROJECT_NAME}}

{{PROJECT_OVERVIEW}}

## 프레임워크 컨벤션 ({{FRAMEWORK}} {{VERSION}})
{{FRAMEWORK_CONVENTIONS_FROM_RESEARCH}}  <!-- 출처: {{SOURCES}} -->

<!-- harness-authoring 주의: 아래 BEGIN/END 두 줄은 apply(upsert_marker_block)가 자동 생성한다.
     plan 의 marker_upsert content 에는 이 두 줄을 넣지 말고 '## 필수 작업 원칙'부터
     마지막 룰 슬롯까지의 body 만 넣을 것(넣으면 중첩 마커가 되어 validate 가 high 로 막는다). -->
<!-- harness:baseline BEGIN (managed by /harness-init — edits inside are overwritten) -->
## 필수 작업 원칙
<!-- rule:karpathy -->
{{KARPATHY_PRINCIPLES}}
<!-- rule:dry-constants -->
{{DRY_CONSTANTS}}
<!-- rule:version-pinning -->
{{VERSION_PINNING}}
<!-- rule:security -->
{{SECURITY}}
<!-- rule:reuse-first -->
{{REUSE_FIRST}}
<!-- harness:baseline END -->

{{FLOW_DEFER_NOTE_IF_FLOW_DETECTED}}
