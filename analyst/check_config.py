#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration health check for portfolios and screens.

Usage:
  STRICT_CONFIG=true python analyst/check_config.py
"""
import os
import sys

def main() -> int:
    # enforce strict config for this check
    os.environ.setdefault('STRICT_CONFIG', 'true')
    try:
        from analyst.portfolios import portfolio_manager
        from analyst.screens import screen_manager
        # Access to trigger validations in constructors
        p_names = portfolio_manager.list_portfolios()
        s_names = screen_manager.list_screens()
        print(f"✅ Portfolios loaded: {p_names}")
        print(f"✅ Screens loaded: {s_names}")
        # Optional weight sanity for DEFAULT
        pm = portfolio_manager
        if 'DEFAULT' in p_names:
            rw = pm.get_recommended_weights('DEFAULT')
            if rw:
                s = sum(float(v) for v in rw.values())
                print(f"ℹ️ DEFAULT recommended weights sum: {s:.6f}")
        print("All checks passed.")
        return 0
    except Exception as e:
        print(f"❌ Config check failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())

