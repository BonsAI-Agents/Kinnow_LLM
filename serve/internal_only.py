"""
Keep /metrics internal (plan sections 11b and 20d: "internal only", 404 or 403 from outside).

Prometheus scrapes the pod directly inside the cluster, so those requests carry no proxy headers.
Anything that arrived through the ingress carries X-Forwarded-For (or a sibling header), so it
is answered with 404 as if the path did not exist. The ingress also only routes /v1 and /health
(k8s/service.yaml); this guard keeps /metrics closed even if the ingress rules are loosened.
"""

from starlette.responses import PlainTextResponse

PROXY_HEADERS = {b'x-forwarded-for', b'x-real-ip', b'forwarded', b'x-forwarded-host'}


class InternalOnly:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            names = {name.lower() for name, _ in scope['headers']}
            if names & PROXY_HEADERS:
                await PlainTextResponse('Not Found', status_code=404)(scope, receive, send)
                return
        await self.app(scope, receive, send)
