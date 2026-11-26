# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Coalesce wheel bursts; never relayout the scroll content on each pixel."""
class SmoothWheel:
    def __init__(self,root,canvas):
        self.root,self.canvas=root,canvas
        self.pending=0;self.scheduled=False
    def feed(self,event):
        delta=getattr(event,'delta',0);number=getattr(event,'num',None)
        pixels=-60 if number==4 else 60 if number==5 else -delta/120*60 if abs(delta)>=120 else -delta*8
        self.pending=max(-600,min(600,self.pending+pixels))
        if not self.scheduled:
            self.scheduled=True;self.root.after(8,self.flush)
        return 'break'
    def flush(self):
        self.scheduled=False
        units=int(self.pending/4)
        if not units:return
        self.pending-=units*4
        try:self.canvas.yview_scroll(units,'units')
        except Exception:self.pending=0
