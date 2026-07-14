"""Deploy-time service registration — run BY `shimpz-app deploy` ON THE BRAIN, never inside the app.

Apps run in their own containers with the registry mounted READ-ONLY (shimpzbus discover/call read it
there); the WRITE happens here, in the trusted plane, right after the deploy health gate passes.
Keep the register() calls below as the single truthful contract of what each role of this project
exposes — a registration is a PROMISE others build on (shimpzbus.call resolves it blindly).
"""

import sys

import shimpzbus

NAME = "shimpz-store"
TOPIC = "shimpz_store.events"  # bus names are SANITIZED (ACL prefix = underscores), app names keep dashes


def main(app_name: str, port: str) -> None:
    if app_name == f"{NAME}-ws":
        shimpzbus.register(
            app_name,
            f"realtime push gateway for {NAME}",
            kind="ws",
            http=f"app_{app_name}:{port}",
            consumes=[TOPIC],
        )
    elif app_name == f"{NAME}-backend":
        shimpzbus.register(
            app_name,
            f"{NAME} API",
            kind="api",
            http=f"app_{app_name}:{port}",
            publishes=[TOPIC],
        )
    else:
        raise SystemExit(
            f"register.py: unknown app name {app_name!r} for project {NAME!r} — add its register() here"
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
