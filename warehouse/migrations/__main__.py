"""Allow running migrations as a module: python -m warehouse.migrations"""

from .run_migrations import main

if __name__ == "__main__":
    main()
