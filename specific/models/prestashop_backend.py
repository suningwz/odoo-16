from odoo import models

class PrestashopBackend(models.Model):
    _inherit = 'prestashop.backend'

    def synchronize_shop_group(self):
        for backend in self:
            for model_name in [
                'prestashop.shop.group',
            ]:
                # import directly, do not delay because this
                # is a fast operation, a direct return is fine
                # and it is simpler to import them sequentially
                self.env[model_name].import_batch(backend)
        return True

    def synchronize_shop(self):
        for backend in self:
            for model_name in [
                'prestashop.shop'
            ]:
                # import directly, do not delay because this
                # is a fast operation, a direct return is fine
                # and it is simpler to import them sequentially
                self.env[model_name].import_batch(backend)
        return True

    def synchronize_res_lang(self):
        for backend in self:
            for model_name in [
                'prestashop.res.lang',
            ]:
                with backend.work_on(model_name) as work:
                    importer = work.component(usage='auto.matching.importer')
                    importer.run()
        return True

    def synchronize_res_country(self):
        for backend in self:
            for model_name in [
                'prestashop.res.country',
            ]:
                with backend.work_on(model_name) as work:
                    importer = work.component(usage='auto.matching.importer')
                    importer.run()
        return True

    def synchronize_res_currency(self):
        for backend in self:
            for model_name in [
                'prestashop.res.currency',
            ]:
                with backend.work_on(model_name) as work:
                    importer = work.component(usage='auto.matching.importer')
                    importer.run()
        return True

    def synchronize_account_tax(self):
        for backend in self:
            for model_name in [
                'prestashop.account.tax',
            ]:
                with backend.work_on(model_name) as work:
                    importer = work.component(usage='auto.matching.importer')
                    importer.run()
            self.env['prestashop.account.tax.group'].import_batch(backend)
            self.env['prestashop.sale.order.state'].import_batch(backend)
        return True
