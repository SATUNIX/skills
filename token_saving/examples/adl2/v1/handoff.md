outcome: done
done:
- add retry with backoff to router client
change:
- router/client.py ; retry idempotent requests 3x with exponential backoff base=200ms ; date=2026-11-03
fact:
- inference API returns 503 above 200 rps ; epistemic=observed ; basis=load test log 2026-11-03
next:
- add circuit breaker to router client ; depends=inference API 503 above 200 rps
ref:
- load test log ; date=2026-11-03 ; artifact=.adl/ev/load-1103.txt
