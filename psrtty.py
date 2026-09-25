import sys

if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--apply-update":
        from psrtty.updater import helper_main
        raise SystemExit(helper_main(sys.argv[2:]))
    from psrtty.app import run
    raise SystemExit(run())
