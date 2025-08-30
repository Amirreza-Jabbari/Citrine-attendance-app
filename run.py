# run.py
import sys
import os

# This is the crucial part that tells Python where to find your package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from citrine_attendance.main import main

if __name__ == '__main__':
    main()
