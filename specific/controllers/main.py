# -*- coding: utf-8 -*-
import logging
from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleSpe(WebsiteSale):

    def _checkout_form_save(self, mode, checkout, all_values):
        if mode[0] == 'new':
            checkout.update({'sale_type': 5})
        partner_id = super(WebsiteSaleSpe, self)._checkout_form_save(mode,
                                                                     checkout,
                                                                     all_values)
        return partner_id
