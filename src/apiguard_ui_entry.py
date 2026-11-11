"""One exe, two modes:  apiguard-ui.exe            -> opens the web UI
                        apiguard-ui.exe scan ...    -> normal command line (used by the UI itself)"""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scan":
        from apiguard.cli import main
        sys.exit(main())
    from demo_ui.app import serve
    serve()
