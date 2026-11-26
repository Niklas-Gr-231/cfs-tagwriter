# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Shared visual tokens and explicit interaction states for both appearances."""
from tkinter import font as tkfont

PALETTES={
    'light':dict(bg='#F4F3F2',surface='#FFFFFF',field='#FAF9F8',fg='#282623',muted='#625D56',border='#DDD8D2',control_border='#8A8077',
                 hover='#EEEAE6',pressed='#E4DBD2',disabled='#817970',accent='#B84016',accent_hover='#99320F',accent_fg='#FFFFFF',
                 focus='#B84016',notice='#FFF0E8',notice_fg='#844019',error_bg='#FCEBE9',error_fg='#9F2630',selection='#B84418'),
    'dark':dict(bg='#242424',surface='#303030',field='#252525',fg='#F7F6F5',muted='#C4C0BB',border='#494644',control_border='#918C86',
                hover='#42403E',pressed='#514A44',disabled='#9C9790',accent='#E95420',accent_hover='#FF6D38',accent_fg='#181818',
                focus='#FF8E63',notice='#493326',notice_fg='#FFD1B5',error_bg='#4A292C',error_fg='#FFC5C5',selection='#B84418'),
}

def contrast(foreground,background):
    def light(hexcolor):
        channels=[int(hexcolor[i:i+2],16)/255 for i in (1,3,5)]
        channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(a*b for a,b in zip(channels,(.2126,.7152,.0722)))
    a,b=sorted((light(foreground),light(background)))
    return (b+.05)/(a+.05)

def apply(root,tk,ttk,dark=False):
    c=dict(PALETTES['dark' if dark else 'light'])
    mode='dark' if dark else 'light'
    if getattr(root,'_cfs_theme_mode',None)!=mode:
        style=ttk.Style(root)
        if style.theme_use()!='clam' and 'clam' in style.theme_names():style.theme_use('clam')
        available=set(tkfont.families(root))
        family=next((name for name in ('Ubuntu','Ubuntu Sans','Inter','Segoe UI Variable','SF Pro Text','Segoe UI','Noto Sans','DejaVu Sans') if name in available),'TkDefaultFont')
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont'):
            tkfont.nametofont(name,root=root).configure(family=family,size=10)
        style.configure('.',font=('TkDefaultFont',10),foreground=c['fg'],background=c['bg'])
        style.configure('TFrame',background=c['bg'])
        style.configure('TLabel',background=c['bg'],foreground=c['fg'])
        style.configure('Title.TLabel',font=(family,23,'bold'))
        style.configure('Hint.TLabel',foreground=c['muted'],background=c['bg'])
        style.configure('Error.TLabel',foreground=c['error_fg'],background=c['error_bg'])
        style.configure('Badge.TLabel',background=c['notice'],foreground=c['notice_fg'],padding=(9,5),font=('TkDefaultFont',9,'bold'))
        style.configure('Notice.TLabel',background=c['notice'],foreground=c['notice_fg'],padding=(12,10))
        style.configure('SuccessNotice.TLabel',background='#163E2C' if dark else '#DDF3E5',foreground='#B8F5CD' if dark else '#185C32',padding=(12,10),font=('TkDefaultFont',11,'bold'))
        style.configure('ErrorNotice.TLabel',background=c['error_bg'],foreground=c['error_fg'],padding=(12,10))
        for prefix,bg in (('',c['bg']),('Card.',c['surface'])):
            style.configure(prefix+'TFrame',background=bg)
            style.configure(prefix+'TLabel',background=bg,foreground=c['fg'])
            style.configure(prefix+'Hint.TLabel',background=bg,foreground=c['muted'])
            style.configure(prefix+'TLabelframe',background=c['surface'],bordercolor=c['border'],lightcolor=c['border'],darkcolor=c['border'],borderwidth=1,relief='solid')
            style.configure(prefix+'TLabelframe.Label',background=c['bg'],foreground=c['fg'],font=('TkDefaultFont',11,'bold'))
            for kind in ('TButton','TMenubutton'):
                name=prefix+kind
                style.configure(name,background=c['surface'],foreground=c['fg'],bordercolor=c['control_border'],lightcolor=c['surface'],darkcolor=c['surface'],borderwidth=1,relief='flat',padding=(13,9),focuscolor=c['focus'])
                style.map(name,background=[('disabled',bg),('pressed',c['pressed']),('active',c['hover']),('!disabled',c['surface'])],
                          foreground=[('disabled',c['disabled']),('active',c['fg']),('!disabled',c['fg'])],
                          bordercolor=[('focus',c['focus']),('active',c['focus']),('!disabled',c['control_border'])],
                          lightcolor=[('active',c['hover'])],darkcolor=[('active',c['hover'])])
            for kind in ('TEntry','TCombobox'):
                name=prefix+kind
                style.configure(name,fieldbackground=c['field'],background=c['field'],foreground=c['fg'],insertcolor=c['fg'],arrowcolor=c['fg'],
                                bordercolor=c['control_border'],lightcolor=c['field'],darkcolor=c['field'],borderwidth=1,padding=(9,7),selectbackground=c['selection'],selectforeground='#FFFFFF')
                style.map(name,fieldbackground=[('disabled',bg),('readonly',c['field']),('!disabled',c['field'])],
                          background=[('disabled',bg),('active',c['hover']),('!disabled',c['field'])],
                          foreground=[('disabled',c['disabled']),('readonly',c['fg']),('!disabled',c['fg'])],
                          bordercolor=[('focus',c['focus']),('active',c['focus']),('!disabled',c['control_border'])],
                          arrowcolor=[('disabled',c['disabled']),('!disabled',c['fg'])])
            for kind in ('TCheckbutton','TRadiobutton'):
                name=prefix+kind
                style.configure(name,background=bg,foreground=c['fg'],focuscolor=c['focus'],bordercolor=c['control_border'],
                                indicatorbackground=c['field'],indicatorforeground=c['fg'],padding=(5,5),indicatormargin=(0,2,8,2),focusthickness=1)
                style.map(name,background=[('disabled',bg),('active',c['hover']),('!disabled',bg)],
                          foreground=[('disabled',c['disabled']),('active',c['fg']),('selected',c['fg']),('!disabled',c['fg'])],
                          indicatorbackground=[('disabled',bg),('selected',c['accent']),('active',c['field']),('!disabled',c['field'])],
                          indicatorforeground=[('disabled',c['disabled']),('selected','#FFFFFF'),('!disabled',c['fg'])],
                          bordercolor=[('focus',c['focus']),('active',c['focus']),('!disabled',c['control_border'])],
                          lightcolor=[('active',c['hover'])],darkcolor=[('active',c['hover'])])
        for name in ('Write.TButton','Card.Write.TButton'):
            style.configure(name,background=c['accent'],foreground=c['accent_fg'],padding=(22,12),borderwidth=0,focuscolor=c['focus'],font=('TkDefaultFont',11,'bold'))
            style.map(name,background=[('disabled',c['border']),('pressed',c['accent_hover']),('active',c['accent_hover']),('!disabled',c['accent'])],
                      foreground=[('disabled',c['disabled']),('!disabled',c['accent_fg'])],
                      bordercolor=[('focus',c['focus'])],lightcolor=[('active',c['accent_hover'])],darkcolor=[('active',c['accent_hover'])])
        style.configure('Treeview',background=c['surface'],fieldbackground=c['surface'],foreground=c['fg'],rowheight=34,bordercolor=c['border'],borderwidth=1)
        style.configure('Treeview.Heading',background=c['hover'],foreground=c['fg'],padding=(10,9),relief='flat',font=('TkDefaultFont',10,'bold'))
        style.map('Treeview',background=[('selected',c['selection'])],foreground=[('selected','#FFFFFF')])
        style.map('Treeview.Heading',background=[('active',c['pressed'])],foreground=[('active',c['fg'])])
        style.configure('TNotebook',background=c['bg'],borderwidth=0)
        style.configure('TNotebook.Tab',background=c['bg'],foreground=c['muted'],padding=(17,10),borderwidth=0)
        style.map('TNotebook.Tab',background=[('selected',c['surface']),('active',c['hover'])],foreground=[('selected',c['fg']),('active',c['fg'])])
        for orientation in ('Vertical','Horizontal'):
            style.configure(orientation+'.TScrollbar',background=c['border'],troughcolor=c['bg'],arrowcolor=c['fg'],borderwidth=0,arrowsize=12)
            style.map(orientation+'.TScrollbar',background=[('active',c['muted'])])
        style.configure('Horizontal.TProgressbar',troughcolor=c['surface'],background=c['accent'],borderwidth=0,thickness=5)
        for key,value in (('background',c['surface']),('foreground',c['fg']),('selectBackground',c['selection']),('selectForeground','#FFFFFF')):
            root.option_add('*TCombobox*Listbox.'+key,value)
        if hasattr(style,'element_create'):
            from cfs_rounded import apply_rounding
            apply_rounding(root,tk,style,c,'dark' if dark else 'light')
        root.configure(background=c['bg'])
        root._cfs_theme_mode=mode
    def recolor(widget,in_card=False):
        card=in_card or isinstance(widget,ttk.LabelFrame)
        if getattr(widget,'_cfs_theme_applied_mode',None)==mode:
            for child in widget.winfo_children():recolor(child,card)
            return
        widget._cfs_theme_applied_mode=mode
        if isinstance(widget,tk.Menu):
            widget.configure(background=c['surface'],foreground=c['fg'],activebackground=c['selection'],activeforeground='#FFFFFF',disabledforeground=c['disabled'],borderwidth=0,activeborderwidth=0)
        elif isinstance(widget,tk.Text):
            widget.configure(background=c['field'],foreground=c['fg'],insertbackground=c['fg'],selectbackground=c['selection'],selectforeground='#FFFFFF',highlightthickness=1,highlightbackground=c['border'],highlightcolor=c['focus'],borderwidth=0)
        elif isinstance(widget,tk.Canvas):
            if not getattr(widget,'_cfs_keep_canvas_colors',False):widget.configure(background=c['bg'])
        elif isinstance(widget,ttk.Widget):
            try:
                original=getattr(widget,'_cfs_original_style',None)
                if original is None:
                    original=widget.cget('style') or widget.winfo_class()
                    if original.startswith('Card.'):original=original[5:]
                    widget._cfs_original_style=original
                if original not in ('Notice.TLabel','SuccessNotice.TLabel','ErrorNotice.TLabel','Badge.TLabel','Title.TLabel','Error.TLabel'):
                    widget.configure(style=('Card.' if card else '')+original)
                # Existing popup listboxes must follow appearance changes too.
                if isinstance(widget,ttk.Combobox):
                    popup=root.tk.call('ttk::combobox::PopdownWindow',str(widget))
                    root.tk.call(str(popup)+'.f.l','configure','-background',c['surface'],'-foreground',c['fg'],'-selectbackground',c['selection'],'-selectforeground','#FFFFFF')
            except tk.TclError:pass
        for child in widget.winfo_children():recolor(child,card)
    recolor(root)
    return c
