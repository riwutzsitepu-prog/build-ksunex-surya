#!/usr/bin/env python3
from pathlib import Path
import sys
root = Path(sys.argv[1] if len(sys.argv) > 1 else 'kernel')
p = root / 'block/mq-deadline.c'
s = p.read_text()
bad = 'static struct request *__dd_dispatch_request(struct deadline_data *dd)\n{\n\tstruct deadline_data *dd = hctx->queue->elevator->elevator_data;\n'
good = 'static struct request *__dd_dispatch_request(struct deadline_data *dd)\n{\n'
if bad in s:
    s = s.replace(bad, good, 1)
    p.write_text(s)
if bad in p.read_text():
    raise SystemExit('mq-deadline duplicate dd still present')
print('mq-deadline duplicate dd: VERIFIED FIXED')
