from odoo import models, fields
from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping


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


class ProductTemplateExportMapper(Component):
    _inherit = 'prestashop.product.template.export.mapper'

    @mapping
    def sizeguide(self, record):
        return {'sizeguide': record.sizeguide}

    @mapping
    def transparency(self, record):
        return {'transparency': record.transparency}

