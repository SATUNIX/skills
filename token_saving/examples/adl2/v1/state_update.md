# v1 state update: staging cluster back, staging GPU confirmed L4

## before

semantic:
m5: staging cluster GPU type is A100 or L4 ; epistemic=disputed ; basis=user,repo:infra/stg.tf

goal: deploy request router to staging cluster
state: doing
done:
- unit tests
doing:
- add retry with backoff to router client ; depends=m2,r2
blocked:
- integration test ; cause=staging cluster unavailable
next:
- request production deploy approval from ops ; depends=m6
risk:
- deployment behavior remains unverified
question:
q1: when is staging cluster back? UNKNOWN.

## after

semantic:
m16: staging cluster GPU type is L4 ; epistemic=observed ; basis=e3 ; supersedes=m5

evidence:
e3: nvidia-smi on staging cluster nodes shows 3x L4 ; date=2026-11-03 ; artifact=.adl/ev/stg-gpu.txt

goal: deploy request router to staging cluster
state: doing
done:
- unit tests
doing:
- add retry with backoff to router client ; depends=m2,r2
- integration test
next:
- request production deploy approval from ops ; depends=m6
risk:
- deployment behavior remains unverified
