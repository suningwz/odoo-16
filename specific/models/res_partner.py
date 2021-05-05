# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models, api
from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def create(self, vals):
        if vals.get("sale_type"):
            sale_type = self.env["sale.order.type"].browse(vals["sale_type"])
            if sale_type.partner_sequence_id:
                vals["ref"] = sale_type.partner_sequence_id.next_by_id()
            if sale_type.id == 5:
                vals['x_studio_typologie_du_contact'] = 'Client Web Odoo'
        return super(ResPartner, self).create(vals)


class PartnerImportMapper(Component):
    _inherit = 'prestashop.res.partner.mapper'

    @mapping
    def studio3(self, record):
        return {'x_studio_typologie_du_contact': "Client B2C"}
