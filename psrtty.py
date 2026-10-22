import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--self-test-skimmer':
        if len(sys.argv) != 3:
            raise SystemExit(2)
        from psrtty.skimmer_selftest import main
        raise SystemExit(main(sys.argv[2]))
    if len(sys.argv) == 5 and sys.argv[1] == "--apply-update":
        from psrtty.updater import helper_main
        raise SystemExit(helper_main(sys.argv[2:]))
    from psrtty.app import run
    raise SystemExit(run())
