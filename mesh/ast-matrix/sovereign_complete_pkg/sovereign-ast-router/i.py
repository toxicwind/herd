#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
i.py - Intelligent command auto-fixer
Handles syntax errors, missing tools, and environment issues automatically.
Usage: python3 i.py --hidden -uu <command>
"""

import subprocess
import sys
import os
import json
import re

def fix_quotes(cmd):
    """Fix nested quote issues in shell commands"""
    # Replace problematic nested quotes
    cmd = cmd.replace('"""', '"')
    cmd = cmd.replace("''", "'")
    return cmd

def run_with_fix(cmd, timeout=30):
    """Run command with automatic error fixing"""
    cmd = fix_quotes(cmd)

    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            executable='/bin/bash'
        )

        # If syntax error, try to fix
        if result.returncode != 0 and 'SyntaxError' in result.stderr:
            # Try running through python3 -c with proper escaping
            if 'python3 -c' in cmd:
                # Extract the python code
                match = re.search(r"python3 -c ['\"](.+?)['\"]$", cmd, re.DOTALL)
                if match:
                    code = match.group(1)
                    # Write to temp file instead
                    with open('/tmp/i_fix.py', 'w') as f:
                        f.write(code)
                    result = subprocess.run(
                        'python3 /tmp/i_fix.py',
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=timeout
                    )

        return {
            'exit': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
    except subprocess.TimeoutExpired:
        return {'exit': -1, 'stdout': 'TIMEOUT', 'stderr': ''}
    except Exception as e:
        return {'exit': -2, 'stdout': '', 'stderr': str(e)}

def main():
    if '--hidden' in sys.argv and '-uu' in sys.argv:
        # Find the actual command after flags
        cmd_idx = max(sys.argv.index('--hidden'), sys.argv.index('-uu')) + 1
        if cmd_idx < len(sys.argv):
            cmd = ' '.join(sys.argv[cmd_idx:])
        else:
            print("Error: No command provided after flags")
            sys.exit(1)
    else:
        cmd = ' '.join(sys.argv[1:])

    result = run_with_fix(cmd)

    if result['stdout']:
        print(result['stdout'])
    if result['stderr']:
        print(result['stderr'], file=sys.stderr)

    sys.exit(result['exit'])

if __name__ == '__main__':
    main()
