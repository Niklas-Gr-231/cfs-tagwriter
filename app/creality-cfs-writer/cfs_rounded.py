# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Original nine-slice Tk graphics: soft corners without extra runtime packages."""
from pathlib import Path


def apply_rounding(root,tk,style,colors,mode):
    folder=Path(__file__).with_name('theme-assets')/mode
    if not (folder/'card.png').is_file():return
    cache=getattr(root,'_cfs_round_images',{})
    if mode not in cache:
        cache[mode]={path.stem:tk.PhotoImage(master=root,file=str(path)) for path in folder.glob('*.png')}
        root._cfs_round_images=cache
    images=cache[mode]
    existing=set(style.element_names())
    def element(name,default,*states,border=23,background=None):
        name='Cfs.'+mode+'.'+name
        if name not in existing:
            def picture(key):
                if background is None:return images[key]
                flat_key='opaque:'+background+':'+key
                if flat_key not in images:
                    source=images[key];flat=tk.PhotoImage(master=root,width=source.width(),height=source.height())
                    flat.put(background,to=(0,0,source.width(),source.height()))
                    root.tk.call(str(flat),'copy',str(source),'-compositingrule','overlay')
                    images[flat_key]=flat
                return images[flat_key]
            style.element_create(name,'image',picture(default),*[(tuple(spec[:-1])+(picture(spec[-1]),)) for spec in states],border=border,padding=0,sticky='nsew')
            existing.add(name)
        return name
    def button_layout(image):
        return [(image,{'sticky':'nsew','children':[('Button.padding',{'sticky':'nsew','children':[('Button.label',{'sticky':'nsew'})]})]})]
    button=element('button','button-normal',('disabled','button-disabled'),('pressed','button-pressed'),('active','button-hover'),('focus','button-focus'),background=colors['bg'])
    primary=element('primary','primary-normal',('disabled','primary-disabled'),('pressed','primary-pressed'),('active','primary-hover'),('focus','primary-focus'),background=colors['bg'])
    entry=element('entry','entry-normal',('disabled','entry-disabled'),('focus','entry-focus'),border=17,background=colors['bg'])
    card=element('card','card',border=26)
    badge=element('badge','badge',border=14)
    notice=element('notice','notice',border=14)
    error=element('error','error',border=14)
    tab=element('tab','tab-normal',('selected','focus','tab-focus'),('selected','tab-selected'),('active','tab-hover'),border=23)
    arrow_padding='Cfs.'+mode+'.arrowpadding'
    if arrow_padding not in existing:
        style.element_create(arrow_padding,'from','clam','Combobox.padding')
        existing.add(arrow_padding)
    check_background=element('check-background','check-bg-normal',('disabled','check-bg-normal'),('active','check-bg-hover'),('focus','check-bg-focus'),border=14)
    checkbox=element('checkbox','check-0-0-0',('disabled','selected','check-1-0-1'),('disabled','check-0-0-1'),('selected','active','check-1-1-0'),('selected','check-1-0-0'),('active','check-0-1-0'),border=0)
    for prefix,bg in (('',colors['bg']),('Card.',colors['surface'])):
        if prefix:
            button=element('card-button','button-normal',('disabled','button-disabled'),('pressed','button-pressed'),('active','button-hover'),('focus','button-focus'),background=bg)
            primary=element('card-primary','primary-normal',('disabled','primary-disabled'),('pressed','primary-pressed'),('active','primary-hover'),('focus','primary-focus'),background=bg)
            entry=element('card-entry','entry-normal',('disabled','entry-disabled'),('focus','entry-focus'),border=17,background=bg)
        # The widget background is the parent's colour; only the image is filled.
        style.layout(prefix+'TButton',button_layout(button))
        style.configure(prefix+'TButton',background=bg)
        style.map(prefix+'TButton',background=[('disabled',bg),('!disabled',bg)])
        style.layout(prefix+'Write.TButton',button_layout(primary))
        style.configure(prefix+'Write.TButton',background=bg)
        style.map(prefix+'Write.TButton',background=[('disabled',bg),('!disabled',bg)])
        style.layout(prefix+'TEntry',[(entry,{'sticky':'nsew','children':[('Entry.padding',{'sticky':'nsew','children':[('Entry.textarea',{'sticky':'nsew'})]})]})])
        style.configure(prefix+'TEntry',background=bg)
        style.map(prefix+'TEntry',background=[('disabled',bg),('!disabled',bg)])
        style.layout(prefix+'TCombobox',[(entry,{'sticky':'nsew','children':[(arrow_padding,{'side':'right','sticky':'ns','children':[('Combobox.downarrow',{'sticky':''})]}),('Combobox.padding',{'sticky':'nsew','children':[('Combobox.textarea',{'sticky':'nsew'})]})]})])
        style.configure(prefix+'TCombobox',background=bg)
        style.map(prefix+'TCombobox',background=[('disabled',bg),('!disabled',bg)])
        style.layout(prefix+'TCheckbutton',[(check_background,{'sticky':'nsew','children':[('Checkbutton.padding',{'sticky':'nsew','children':[(checkbox,{'side':'left','sticky':'w'}),('Checkbutton.focus',{'side':'left','sticky':'w','children':[('Checkbutton.label',{'sticky':'nsew'})]})]})]})])
        style.configure(prefix+'TCheckbutton',background=bg)
        style.map(prefix+'TCheckbutton',background=[('disabled',bg),('!disabled',bg)])
        style.layout(prefix+'TLabelframe',[(card,{'sticky':'nsew'})])
        style.configure(prefix+'TLabelframe',background=colors['bg'])
    progress_trough=element('Horizontal.Progressbar.trough','progress-trough',border=(6,0,6,0))
    progress_fill=element('Horizontal.Progressbar.pbar','progress-fill',border=(6,0,6,0))
    style.layout('Horizontal.TProgressbar',[(progress_trough,{'sticky':'nsew','children':[(progress_fill,{'side':'left','sticky':'ns'})]})])
    style.configure('Horizontal.TProgressbar',background=colors['bg'],borderwidth=0)
    for orientation in ('Vertical','Horizontal'):
        lower=orientation.lower()
        thumb=element(lower+'.Scrollbar.thumb','scroll-'+lower+'-normal',('disabled','scroll-'+lower+'-disabled'),('pressed','scroll-'+lower+'-pressed'),('active','scroll-'+lower+'-hover'),border=(0,6,0,6) if orientation=='Vertical' else (6,0,6,0))
        name=orientation+'.TScrollbar'
        style.layout(name,[(orientation+'.Scrollbar.trough',{'sticky':'nsew','children':[(thumb,{'expand':1,'sticky':'nsew'})]})])
        style.configure(name,background=colors['bg'],troughcolor=colors['bg'],bordercolor=colors['bg'],lightcolor=colors['bg'],darkcolor=colors['bg'],borderwidth=0,arrowsize=0)
        style.map(name,background=[('active',colors['bg']),('!disabled',colors['bg'])])
    for name,image in (('Badge.TLabel',badge),('Notice.TLabel',notice),('ErrorNotice.TLabel',error)):
        style.layout(name,[(image,{'sticky':'nsew','children':[('Label.padding',{'sticky':'nsew','children':[('Label.label',{'sticky':'nsew'})]})]})])
        style.configure(name,background=colors['bg'])
    style.layout('TNotebook.Tab',[(tab,{'sticky':'nsew','children':[('Notebook.padding',{'sticky':'nsew','children':[('Notebook.label',{'sticky':'nsew'})]})]})])
