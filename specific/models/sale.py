# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import mapping


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.depends("partner_id", "company_id")
    def _compute_sale_type_id(self):
        for record in self:
            if not record.partner_id:
                record.type_id = self.env["sale.order.type"].search(
                    [("company_id", "in", [self.env.company.id, False])], order='id desc', limit=1
                )
            else:
                sale_type = (
                    record.partner_id.with_context(
                        force_company=record.company_id.id
                    ).sale_type
                    or record.partner_id.commercial_partner_id.with_context(
                        force_company=record.company_id.id
                    ).sale_type
                )
                if sale_type:
                    record.type_id = sale_type
                if sale_type.id == 5:
                    record.x_studio_type_de_livraison = "Log'ins"
                    record.x_studio_statut_rsilience = "Envoyé à l’entrepôt"

    @api.onchange("type_id")
    def onchange_type_id(self):
        super(SaleOrder, self).onchange_type_id()
        for order in self:
            order_type = order.type_id
            if order_type.workflow_process_id:
                order.update({'workflow_process_id': order_type.workflow_process_id})
            if order_type.id == 5:
                order.update({"x_studio_type_de_livraison": "Log'ins",
                              "x_studio_statut_rsilience": "Envoyé à l’entrepôt"})


class SaleOrderImportMapper(Component):
    _inherit = 'prestashop.sale.order.mapper'

    @mapping
    def studio1(self, record):
        return {'x_studio_statut_rsilience': "Envoyé à l’entrepôt"}

    @mapping
    def studio2(self, record):
        return {'x_studio_type_de_livraison': "Log'ins"}

    """@mapping
    def studio3(self, record):
        return {'x_studio_typologie_du_contact': "Client B2C"}"""
