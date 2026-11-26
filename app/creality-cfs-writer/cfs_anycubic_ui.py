# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Compatibility entry point; Anycubic now uses the common main tag form."""


def show(app, tk, ttk, dialogs, *, printer=None):
    return app.show_anycubic(printer=printer)
