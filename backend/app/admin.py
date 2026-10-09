"""Site admin tasks from the server's command line, for setting up a new installation.

    python -m app.admin invite EMAIL   print a sign-up link for a new coach (nothing is emailed)
    python -m app.admin grant EMAIL    make an existing account a site admin
    python -m app.admin revoke EMAIL   take site admin away

On a new server: invite yourself, open the link to create your account, then grant yourself admin. From then on,
new clubs are invited from Settings in the app.
"""
import argparse
import sys
from . import invites
from .config import settings
from .database import SessionLocal
from .models import AuthToken, User


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description="Site admin tasks.")
    parser.add_argument("action", choices=["invite", "grant", "revoke"])
    parser.add_argument("email")
    args = parser.parse_args(argv)
    email = args.email.strip().casefold()
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).first()
        if args.action == "invite":
            if user:
                print(f"{email} already has an account.", file=sys.stderr)
                return 1
            db.query(AuthToken).filter_by(email=email, purpose="signup").delete(synchronize_session=False)
            token, _ = invites.issue(db, email, "signup", invites.SITE_INVITE_DAYS)
            db.commit()
            print(f"Sign-up link for {email}, valid for {invites.SITE_INVITE_DAYS} days:\n{settings.public_base_url}/invite/{token}")
            return 0
        if not user:
            print(f"No account for {email}.", file=sys.stderr)
            return 1
        user.is_admin = args.action == "grant"
        db.commit()
        print(f"{email} is {'now' if user.is_admin else 'no longer'} a site admin.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
