# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Main-window pages; keep the tag form and reader state alive while navigating."""


def open_page(app,tk,ttk,title,*,scroll=False):
    close=getattr(app,'close_main_page',None)
    if close:close()
    packed=[(widget,widget.pack_info()) for widget in app.root.pack_slaves()]
    for widget,_ in packed:widget.pack_forget()
    page=ttk.Frame(app.root);page.pack(fill='both',expand=True)
    old_min=app.root.minsize();app.root.minsize(1000,700)
    bar=ttk.Frame(page,padding=(18,10));bar.pack(fill='x')
    viewport=ttk.Frame(page);viewport.pack(fill='both',expand=True)
    if scroll:
        canvas=tk.Canvas(viewport,highlightthickness=0,yscrollincrement=4)
        scrollbar=ttk.Scrollbar(viewport,orient='vertical',command=canvas.yview)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body=ttk.Frame(canvas)
        item=canvas.create_window((0,0),window=body,anchor='nw')
        geometry=[None]
        def fit(_event=None):
            size=(max(1,canvas.winfo_width()),max(canvas.winfo_height(),body.winfo_reqheight()))
            if geometry[0]!=size:
                geometry[0]=size;canvas.itemconfigure(item,width=size[0],height=size[1]);canvas.configure(scrollregion=(0,0,*size))
        body.bind('<Configure>',fit);canvas.bind('<Configure>',fit)
        from cfs_scroll import SmoothWheel
        wheel=SmoothWheel(app.root,canvas)
        def feed(event):
            if not isinstance(event.widget,(tk.Text,ttk.Combobox,ttk.Treeview,ttk.Scrollbar)):return wheel.feed(event)
        bindings=[(event,app.root.bind(event,feed,add='+')) for event in ('<MouseWheel>','<Button-4>','<Button-5>')]
        def cleanup(event):
            if event.widget is viewport:
                for sequence,identifier in bindings:app.root.unbind(sequence,identifier)
        viewport.bind('<Destroy>',cleanup)
    else:
        body=viewport
    def close():
        if app.busy:return
        page.destroy();app.root.minsize(*old_min)
        for widget,options in packed:
            if widget.winfo_exists():widget.pack(**options)
        app.close_main_page=None
        app.apply_theme(persist=False)
    back=ttk.Button(bar,text='← Tagwriter',command=close);back.pack(side='left')
    ttk.Label(bar,text=title,font=('TkDefaultFont',14,'bold')).pack(side='left',padx=16)
    appearance=ttk.Button(bar,text='Hell' if app.theme_var.get()=='dark' else 'Dunkel',command=app.toggle_appearance)
    appearance.pack(side='right')
    trace=app.theme_var.trace_add('write',lambda *args:appearance.configure(text='Hell' if app.theme_var.get()=='dark' else 'Dunkel'))
    def destroyed(event):
        if event.widget is page:app.theme_var.trace_remove('write',trace)
    page.bind('<Destroy>',destroyed)
    app.close_main_page=close
    app.main_page_fields={'body':body,'back':back,'appearance':appearance,'title':title}
    app.apply_theme(persist=False)
    return body,close
