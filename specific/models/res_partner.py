# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def create(self, vals):
        if vals.get("sale_type"):
            sale_type = self.env["sale.order.type"].browse(vals["sale_type"])
            if sale_type.partner_sequence_id:
                vals["ref"] = sale_type.partner_sequence_id.next_by_id()
        return super(ResPartner, self).create(vals)
