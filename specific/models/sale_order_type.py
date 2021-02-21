# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class SaleOrderTypology(models.Model):
    _inherit = "sale.order.type"

    workflow_process_id = fields.Many2one(
        comodel_name="sale.workflow.process",
        string="Flux Automatique",
        ondelete="restrict",
    )
    partner_sequence_id = fields.Many2one(
        comodel_name="ir.sequence",
        string="Partner Sequence",
        copy=False,
    )
