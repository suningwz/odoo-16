# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def submit_for_approval(self):
        for rec in self:
            rec.state = 'waiting_for_approval'

    def action_confirm(self):
        for rec in self:
            print(rec.state)
            if rec.state == 'sent' and rec.require_signature:
                return rec.submit_for_approval()
            else:
                return super(SaleOrder, rec).action_confirm()

    state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('waiting_for_approval', 'Waiting For Approval'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
