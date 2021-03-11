from odoo import models, fields


class PrestashopProductTemplate(models.Model):
    _inherit = 'prestashop.product.template'

    sizeguide = fields.Html(
        string='Sizeguide',
        translate=True,
        help="Sizeguide",
    )

    transparency = fields.Html(
        string='Transparency',
        translate=True,
        help="Transparency",
    )

