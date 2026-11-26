# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Themed in-window dropdowns, using the existing menu actions and states."""
def mount(app, parent, tk, ttk, menus):
    frame = ttk.Frame(parent)
    frame.grid(row=2, column=0, columnspan=4, sticky='ew', pady=(12, 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=0, column=0, sticky='ew')
    frame.columnconfigure(0, weight=1)
    panel = ttk.Frame(frame, padding=10, style='Card.TFrame')
    state = {'open': None}
    controls = []

    def close(_event=None):
        panel.grid_remove()
        state['open'] = None
        for title, button in controls:
            button.configure(text=title+' ▾')

    def toggle(title, menu):
        if app.busy or state['open'] == title:
            close()
            return
        close()
        state['open'] = title
        for name, button in controls:
            button.configure(text=name+(' ▴' if name == title else ' ▾'))
        for child in panel.winfo_children():
            child.destroy()
        last = menu.index('end')
        if last is None:
            return
        for index in range(last+1):
            if menu.type(index) != 'command':
                continue
            def invoke(index=index):
                close()
                menu.invoke(index)
            ttk.Button(panel, text=menu.entrycget(index, 'label'), command=invoke,
                       state=menu.entrycget(index, 'state')).pack(fill='x', pady=3)
        panel.grid(row=1, column=0, sticky='ew', pady=(8, 0))

    for column, (title, menu) in enumerate(menus):
        buttons.columnconfigure(column, weight=1, uniform='navigation')
        button = ttk.Button(buttons, text=title+' ▾', style='Write.TButton',
                            command=lambda title=title, menu=menu: toggle(title, menu))
        button.grid(row=0, column=column, sticky='ew', padx=(0, 8 if column < len(menus)-1 else 0))
        controls.append((title, button))
        app.controls.append((button, 'normal'))
    app.root.bind('<Escape>', close, add='+')
    app.root.configure(menu='')
    return {'frame': frame, 'panel': panel, 'buttons': controls, 'close': close, 'toggle': toggle}
