# Copyright 2021 Romain Deheele
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import io, csv
import base64
import ftplib
import paramiko
from datetime import datetime
import pytz
from dateutil.relativedelta import relativedelta
from odoo import fields, models, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_approve(self, force=False):
        result = super(PurchaseOrder, self).button_approve(force=force)
        if self.picking_ids:
            self.env['ftp.event'].create({'picking_id': self.picking_ids[0].id,
                                          'ftp_type': 'REC_OUT'})
        return result


class FtpBackend(models.Model):
    _name = 'ftp.backend'

    name = fields.Char('FTP Backend')
    host = fields.Char('URL')
    port = fields.Integer('Port')
    username = fields.Char('Username')
    password = fields.Char('Password')


class FtpEvent(models.Model):
    _name = "ftp.event"
    _order = "id desc"

    def _compute_name(self):
        for event in self:
            if event.picking_id:
                event.name = event.picking_id.name
            else:
                event.name = ''

    name = fields.Char('Name', compute='_compute_name')
    ftp_type = fields.Selection([('SHIP_OUT', 'SHIP_OUT'), ('REC_OUT', 'REC_OUT'), ('SHIP_IN', 'SHIP_IN')], 'Type', default='SHIP_OUT')
    state = fields.Selection([('draft', 'Draft'), ('ready', 'Ready'), ('done', 'Done')], 'State', default='draft')
    job_id = fields.Many2one('ftp.job', 'Job')
    picking_id = fields.Many2one('stock.picking', 'Picking')
    sale_id = fields.Many2one('sale.order', related='picking_id.sale_id', string='Sale Order')
    partner_id = fields.Many2one('res.partner', related='picking_id.partner_id', string='Partner')
    tracking_number = fields.Char('Tracking Number')

    @api.onchange('ftp_type')
    def onchange_ftp_type(self):
        for rec in self:
            if rec.ftp_type == 'SHIP_OUT':
                return {'domain': {'picking_id': [('picking_type_id', '=', 2),('state','=','assigned')]}}
            if rec.ftp_type == 'REC_OUT':
                return {'domain': {'picking_id': [('picking_type_id', '=', 1),('state','=','assigned')]}}

    def action_done(self):
        if self.ftp_type == 'SHIP_IN':
            if not self.picking_id.carrier_tracking_ref:
                if self.tracking_number:
                    self.picking_id.write({'carrier_tracking_ref': self.tracking_number})
            if self.picking_id.state not in ['done','cancel']:
                self.picking_id.validate_picking()
        self.write({'state': 'done'})

    def execute_ready_in_events(self):
        ready_in_events = self.search([('ftp_type','like','%IN'), ('state','=','ready')])
        for event in ready_in_events:
            event.action_done()
        return True


class FtpJob(models.Model):
    _name = "ftp.job"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _order = "id desc"

    def _compute_name(self):
        for job in self:
            if job.ftp_type == 'SHIP_IN':
                attachment = self.env['ir.attachment'].search([('res_model','=','ftp.job'),('res_id','=',job.id)])
                job.name = attachment.name
            else:
                tz = pytz.timezone('Europe/Paris')
                to_datetime = pytz.utc.localize(job.to_datetime).astimezone(tz)
                job.name = job.ftp_type + ' ' + to_datetime.strftime("%Y-%m-%d %H:%M:%S")

    name = fields.Char('Name', compute='_compute_name')
    ftp_type = fields.Selection([('BARCODE_OUT', 'Barcode OUT'),
                                 ('PRODUCT_OUT', 'Product OUT'),
                                 ('PRODUCT_IN', 'Product IN'),
                                 ('SHIP_OUT', 'Shipping OUT'),
                                 ('REC_OUT', 'Receiving OUT'),
                                 ('MVT_OUT', 'Movement OUT'),
                                 ('SHIP_IN', 'Shipping IN'),
                                 ('REC_IN', 'Receiving IN'),
                                 ('MVT_IN', 'Movement IN')], 'Ftp Type')
    to_datetime = fields.Datetime('To Datetime', default=fields.Datetime.now)
    from_datetime = fields.Datetime('From Datetime')
    state = fields.Selection([('draft', 'Draft'),
                              ('progress', 'Progress'),
                              ('ready', 'Ready'),
                              ('done', 'Done')], 'State', default='draft')
    event_ids = fields.One2many('ftp.event', 'job_id', 'Events')
    product_ids = fields.Many2many('product.product', string='Products')

    def _scheduler_ftp_in_action_ready(self):
        draft_jobs = self.search([('ftp_type', '=', 'SHIP_IN'), ('state', '=', 'draft')])
        for job in draft_jobs:
            job.action_plan()
        return True

    def _scheduler_ftp_in_action_done(self):
        ready_jobs = self.search([('ftp_type', '=', 'SHIP_IN'), ('state', '=', 'ready')])
        for job in ready_jobs:
            job.action_done()
        return True

    def _scheduler_ftp_out_action_done(self):
        ready_jobs = self.search([('ftp_type', '=', 'SHIP_OUT'), ('state', '=', 'ready')])
        for job in ready_jobs:
            job.action_done()
        return True

    def _scheduler_ftp_import_in_files(self):
        self.action_receive_files('/IN/RES/CR_PRE/', 'SHIP_IN')
        #self.action_receive_files('/IN/RES/CR_REC/', 'REC_IN')
        #self.action_receive_files('/IN/RES/CR_MVT/', 'MVT_IN')
        return True

    def _scheduler_ftp_export_products(self):
        self.create({'ftp_type': 'PRODUCT_OUT', 'state': 'progress'})

    def _scheduler_ftp_export_barcodes(self):
        self.create({'ftp_type': 'BARCODE_OUT', 'state': 'progress'})

    def _set_datetime_job(self, ftp_type, from_datetime):
        now = fields.Datetime.now()
        #from_datetime = now - relativedelta(minutes=interval_number)
        new_job = self.create({'ftp_type': ftp_type,
                             'from_datetime': from_datetime,
                             'to_datetime': now,
                             'state': 'draft'})
        return new_job

    def _scheduler_ftp_export_shipping(self):
        last_job = self.search([('ftp_type','=','SHIP_OUT')], order='id desc', limit=1)
        from_datetime = last_job and last_job.to_datetime or False
        new_job = self._set_datetime_job('SHIP_OUT', last_job.to_datetime)
        new_job.action_plan()

    def _scheduler_ftp_export_receiving(self, interval_numer):
        last_job = self.search([('ftp_type','=','REC_OUT')], order='id desc', limit=1)
        from_datetime = last_job and last_job.to_datetime or False
        self._set_datetime_job('REC_OUT')

    def parse_ship_in_attachment(self):
        attachment = self.env['ir.attachment'].search([('res_model','=','ftp.job'),('res_id','=',self.id)])
        content = base64.b64decode(attachment[0].datas)
        reader = csv.reader(content.decode('iso-8859-1').split('\n'), delimiter=';')
        for row in reader:
            if row:
                if row[0] == 'ENT':
                    sale_name = row[3]
                if row[0] == 'COL':
                    tracking = row[8].strip()
        sale = self.env['sale.order'].search([('name','=',sale_name)])
        if sale:
            if sale.picking_ids:
                for pick in sale.picking_ids:
                    if pick.picking_type_id.id == 2 and tracking:
                        self.env['ftp.event'].create({'picking_id': pick.id, 'job_id': self.id,
                                                      'ftp_type': 'SHIP_IN', 'tracking_number': tracking, 'state': 'ready'})
            return True
        return False

    def action_plan(self):
        if self.ftp_type in ['BARCODE_OUT','PRODUCT_OUT']:
            if self.product_ids:
                self.write({'state': 'progress'})
        elif 'OUT' in self.ftp_type:
            #add events
            event_ids = self.env['ftp.event'].search([('ftp_type', '=', self.ftp_type),
                                                      ('create_date', '<=', self.to_datetime),
                                                      ('create_date', '>=', self.from_datetime),
                                                      ('job_id','=', False)])
            if event_ids or self.event_ids:
                event_ids.write({'job_id': self.id})
                self.write({'state': 'progress'})
                self.action_make_file()
            else:
                self.write({'state': 'done'})
        elif 'IN' in self.ftp_type:
            if self.parse_ship_in_attachment():
                self.write({'state': 'ready'})
        else:
            self.write({'state': 'done'})

    def _prepare_barcode_out_datas(self):
        datas = []
        datas.append(['Société/company', 'Entrepôt/warehouse', 'Réservé Spidy/Spidy reserved',
                      'Client propriétaire/owner code', 'Code produit/product code', 'Code à barre/Barcode',
                      'Quantité/quantity', 'Code unité/Unit code', 'Adresse email erreurs/Errors email adress'])
        #product_ids = self.env['product.product'].search([('sale_ok', '=', True)])
        for product in self.product_ids:
            datas.append(['ASF', 'LVD', '', 'RES', product.default_code, product.barcode, '', '', 'si@projet-resilience.fr'])
        return datas

    def _prepare_product_out_datas(self):
        datas = []
        datas.append(['Société', 'Entrepôt', 'Erreurs (réservé Spidy)', 'Client Propriétaire',
                      'Code Produit (majuscules)', 'Réservé SPIDY', 'Désignation article', 'Caractéristiques articles',
                      'Référence fournisseur', 'Non utilisé', 'Code Unité de stock', 'Libellé Unt stockage',
                      'Palettisation', 'Hauteur palette', 'Largeur palette', 'Profondeur palette', 'Poids total palette',
                      'Code Tri préparation', 'Sous / combien', 'Colisage / par combien', 'Poids unité de stock',
                      'Gestion des lots', 'Code emballage', 'Non utilisé', 'Non utilisé', 'Non utilisé',
                      'Prix valorisation', 'Coefficient', 'Code Fournisseur', 'Gamme produit', 'Gestion picking UVC',
                      'Code unité UVC', 'Libellé unité UVC', 'Typologie stockage reserve', 'Typologie réserve Imposée',
                      'Typologie stockage picking', 'Typologie picking Imposée', 'Capture Code barre en reception',
                      'Colisage Unité d\'oeuvre', 'Colisage Hauteur', 'Colisage Largeur', 'Colisage Profondeur',
                      'UVC unité d\'oeuvre', 'UVC Hauteur', 'UVC Largeur', 'UVC Profondeur', 'Niv colisage', 'Code Kit article',
                      'Code contrôle article en reception', 'Nb de n° de série', 'Niveau Stock d\'alerte',
                      'Type de gestion d\'emplacement', 'Code statut produit', 'Code état enregistrement', 'Réservé spidy',
                      'Réservé spidy', 'Réservé spidy', 'email erreur', 'Mode gestion lot', 'Gestion date 1', 'Gestion date 2', 'Gestion date 3',
                      'Delai mini entre date rec et dte lot 1', 'Delai mini entre date rec et dte lot 2', 'Delai mini entre date rec et dte lot 3',
                      'Libell_ date 1', 'Libell_ date 2', 'Libell_ date 3', 'Interdict lot depass', 'Type gestion lot', 'Emplacement Picking fixe',
                      'Lien HTTP fiche produit', 'Fiche technique ligne 1', 'Fiche technique ligne 2', 'Fiche technique ligne 3', 'Fiche technique ligne 4',
                      'Fiche technique ligne 5', 'Fiche technique ligne 6', 'Fiche technique ligne 7', 'Fiche technique ligne 8', 'Fiche technique ligne 9',
                      'Fiche technique ligne 10', 'Fiche technique ligne 11', 'Fiche technique ligne 12', 'Fiche technique ligne 13',
                      'Fiche technique ligne 14', 'Fiche technique ligne 15', 'Fiche technique ligne 16', 'Fiche technique ligne 17',
                      'Fiche technique ligne 18', 'Fiche technique ligne 19', 'Fiche technique ligne 20', 'Gamme alcool', 'Degr_ alcool pur',
                      'Volume effectif (litre)', 'Type gestion d\'alcool', 'R_serv_'])
        #product_ids = self.env['product.product'].search([('sale_ok', '=', True)])
        for product in self.product_ids:
            datas.append(['ASF', 'LVD', '', 'RES', product.default_code, '', product.name, '', '', '', 'UN', 'Unité', 1,
                          '', '', '', '', '', '', 1, product.weight, '', '', '', '', '', product.list_price, 1,
                          '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '',
                          '', '', '', '2', '', 'AT', '', '', '', 'logistique@projet-resilience.fr',
                          '', '', '', '', '', '', '', '', '', '', '', '', '',
                          '', '', '', '', '', '', '', '', '', '', '', '', '',
                          '', '', '', '', '', '', '', '', '', '', '', '', ''])
        return datas

    def _prepare_ship_out_datas(self):
        datas = []
        datas.append(['Reserve_Spidy_Spidy_reserved', 'Societe_company', 'Entrepot_Warehouse', 'Numero_commande_client__Order_number',
                      'Code_client___Customer_code', 'Raison_sociale___Company_name',
                      'Adresse_livraison_1___Shipping_address_1', 'Adresse_livraison_2___Shipping_address_2', 'Adresse_livraison_3___shipping_address_3',
                      'Code_postal___Shipping_Postal_Code', 'Ville____Shipping_Town', 'Code_pays___shippping_country_code',
                      'Initiateur_commande___Order_initiator', 'Commentaire_transport___Shipping_comment_1', 'Commentaire_2___Shipping_Comment_2',
                      'Commentaire_3___Shipping_comment_2', 'Type_de_commande___Order_type',
                      'Siecle_livraison___delivery_century', 'Date_livraison___delivery_date',
                      'Pre_tournee___Shipping_route', 'Tour_de_livraison___Shipping_turn', 'Priorite_missions___Priority',
                      'Type_date_si_calcul_auto_priorite___Date_type_for_automatic_priority_calculation',
                      'Type_priorite___Priority_type', 'Passage_par_portefeuille_impose___Force_order_portfolio',
                      'Type_de_mouvement___Order_type_of_stock', 'Mention_etiquette_expedition___Shipping_label_header',
                      'Contre_remboursement_ou_assurance___Payment_at_delivery_time_or_insurance',
                      'Montant_contre_remboursement__ou_assurance___Amount_to_be_paid_at_delivery_time_or_insurance_amount',
                      'Mode_de_tri_preparation_assistee___Picking_sort_type', 'Code_expediteur_EDI___EDI_shipping_account',
                      'Numero_de_ligne___Line_number', 'Code_article___Product_code',
                      'Numero_de_lot___Batch_number', 'Quantite_a_expedier___Quantity_to_ship',
                      'Reserve_Spidy_Spidy_reserved1', 'Commentaire_ligne_produit___Product_line_comment', 'Prix_unitaire_valorisation___Sale_price_for_labels',
                      'Adresse_email_erreur___Error_email_address',
                      'Adresse_alternative_1___Alternate_address_1', 'Adresse_alternative_2___Alternate_address_2',
                      'Adresse_alternative_3___Alternate_address_3', 'Adresse_alternative_4___Alternate_address_4',
                      'Adresse_alternative___code_postal___Alternate_address___zip_code','Adresse_alternative___ville___Alternate_Address___City',
                      'Adresse_alternative___code_pays___Alternate_address___Country', 'Code_porte___Gate_code', 'Code_porte_2___Gate_code_2',
                      'Interphone___Intercom', 'Telephone_Portable___Cellular_phone', 'Telephone_fixe___Fixed_phone',
                      'Zone_complementaire_specifique_transporteur_Carrier_complement', 'Commentaire_commande_complementaire_1___Order_additionnal_comment_1',
                      'Impression_commentaire_comp_1_sur_BL___print_additionnal_comment_1_on_delivery_note',
                      'Commentaire_commande_complementaire_2___Order_additionnal_comment_2',
                      'Impression_commentaire_comp_2_sur_BL___print_additionnal_comment_2_on_delivery_note',
                      'Commentaire_commande_complementaire_3___Order_additionnal_comment_3',
                      'Impression_commentaire_comp_3_sur_BL___print_additionnal_comment_3_on_delivery_note',
                      'Commentaire_commande_complementaire_4___Order_additionnal_comment_4',
                      'Impression_commentaire_comp_4_sur_BL___print_additionnal_comment_4_on_delivery_note',
                      'Commentaire_commande_complementaire_5___Order_additionnal_comment_5',
                      'Impression_commentaire_comp_5_sur_BL___print_additionnal_comment_5_on_delivery_note',
                      'Destinataire_commande___Order_consignee', 'Type_de_client___Customer_type', 'Identifiant_1___identifier_1',
                      'Identifiant_2___identifier_2', 'Identifiant_3___identifier_3', 'Type_d_adresse___Adress_type', 'Code_agence___Agency_code'])
        for event in self.event_ids:
            pick = event.picking_id
            line_nb = 0
            for line in pick.move_lines:
                line_nb += 1
                sale = pick.sale_id
                partner = pick.partner_id
                carrier_code = pick.carrier_id and pick.carrier_id.ftp_code or 'INT'
                datas.append(['', 'ASF', 'LVD', sale.name, 'RES', partner.name.replace('’',' ') or '', partner.street.replace('’',' ') or '',
                              partner.street2.replace('’',' ') or '', '', partner.zip or '', partner.city.replace('’',' ') or '',
                              partner.country_id and partner.country_id.code or '', '', '',
                              partner.parent_id and partner.parent_id.email or partner.email or '', '', '', 1,
                              pick.scheduled_date and (pick.scheduled_date.strftime('%y%m%d')) or '',
                              carrier_code, '', '', '', '', '', '1', '', '', '', '', 'RES',
                              line_nb, line.product_id and line.product_id.default_code or '', '', int(line.product_uom_qty) or '', '', '',
                              line.product_id and str(line.product_id.standard_price).replace('.',',') or '0,0',
                              'logistique@projet-resilience.fr','','','','','','','','','','',
                              partner.phone or '', '','','','','','','','','','','','','','','','','','',''])
        return datas

    def _prepare_rec_out_datas(self):
        datas = []
        datas.append(['Réservé SPIDY', 'Société', 'Entrepôt', 'Type d\'entrée', 'Nature de l\'entrée marchandise',
                      'N° de reference de l\'entrée attendue', 'Siecle', 'Date entrée prévisionnelle', 'Raison sociale vendeur',
                      'Client propriétaire', 'Flag suppression entrée previ', 'Code fournisseur', 'Retour : code client',
                      'Retour : adresse 1', 'Retour : adresse 2', 'Retour : adresse 3', 'Retour : code postal',
                      'Retour : ville', 'Retour : Pays', 'retour : commentaire', 'Code article', 'Quantité', 'adresse email erreur'])
        for event in self.event_ids:
            pick = event.picking_id
            for line in pick.move_lines:
                datas.append(['', 'ASF', 'ATS', 'R', '', 'ATE/' + pick.name, '' , '', '', 'RES', '',
                              line.product_id.default_code, '', '', '', '', '', '', '', '',
                              line.product_id.default_code, line.product_uom_qty, 'logistique@projet-resilience.fr'])
        return datas

    def _prepare_datas(self):
        if self.ftp_type == 'BARCODE_OUT':
            datas = self._prepare_barcode_out_datas()
        elif self.ftp_type == 'PRODUCT_OUT':
            datas = self._prepare_product_out_datas()
        elif self.ftp_type == 'SHIP_OUT':
            datas = self._prepare_ship_out_datas()
        elif self.ftp_type == 'REC_OUT':
            datas = self._prepare_rec_out_datas()
        else:
            datas = []
        return datas

    def action_make_file(self):
        datas = self._prepare_datas()
        if datas:
            f = io.StringIO()
            writer = csv.writer(f, delimiter=';', quotechar='"')
            for data in datas:
                writer.writerow(data)
            content = base64.encodebytes(f.getvalue().encode('iso-8859-1'))
            tz = pytz.timezone('Europe/Paris')
            to_datetime = pytz.utc.localize(self.to_datetime).astimezone(tz)
            attachment = self.env['ir.attachment'].create({
                'datas': content,
                'name': self.ftp_type + ' ' + to_datetime.strftime("%Y-%m-%d %H:%M:%S") + '.csv',
                'type': 'binary',
                'res_id': self.id,
                'res_model': 'ftp.job'
            })
            self.write({'state': 'ready'})
            self.event_ids.write({'state': 'ready'})

    """def make_file2(self):
        home = '/tmp/'
        filename = self.ftp_type + '_' + self.to_datetime.strftime("%Y-%m-%d% H:%M:%S") + '.csv'
        path_file = home + filename
        with open(path_file, 'w') as fp:
            a = csv.writer(fp, delimiter=';')
            a.writerows(data)
        self.write({'data': data,
                    'name': filename,
                    'ftp_file': base64.b64encode(open(path_file, 'rb').read())
                    })"""

    """def ftp_connect(self):
        backend = self.env['ftp.backend'].search([],limit=1)
        from ftplib import FTP
        ftp = FTP(backend.host)
        ftp.login(user=backend.username, passwd=backend.password)
        return ftp"""

    def action_receive_files(self, remote_path, ftp_type):
        backend = self.env['ftp.backend'].search([],limit=1)
        host,port = backend.host,backend.port
        transport = paramiko.Transport((host,port))
        transport.connect(None, backend.username, backend.password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        filenames = sftp.listdir('/RES/IN/RES/CR_PRE/')
        for filename in filenames:
            sftp.get('/RES/IN/RES/CR_PRE/' + filename, '/tmp/' + filename)
        for filename in filenames:
            att_id = self.env['ir.attachment'].search([('name','=',filename),('res_model','=','ftp.job')])
            if not att_id:
                with open('/tmp/' + filename, 'rb') as f:
                    content = f.read()
                    job_id = self.create({'ftp_type': ftp_type,
                                          'to_datetime': fields.Datetime.now(),
                                          'state': 'draft'})
                    attachment = self.env['ir.attachment'].create({
                        'datas': base64.b64encode(content),
                        'name': filename,
                        'type': 'binary',
                        'res_id': job_id,
                        'res_model': 'ftp.job'
                    })
                    job_id.action_plan()
        return True

    def action_send_file(self):
        backend = self.env['ftp.backend'].search([],limit=1)
        host,port = backend.host,backend.port
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, port, backend.username, backend.password)
        sftp = ssh.open_sftp()

        attachment = self.env['ir.attachment'].search([('res_model', '=', 'ftp.job'),
                                                       ('res_id', '=', self.id)],
                                                      order='id desc', limit=1)
        remote_path = '/RES/OUT/' + attachment.name.replace(' ','_').replace(':','')
        local_path = attachment._full_path(attachment.store_fname)

        sftp.put(local_path, remote_path)

        sftp.close()
        ssh.close()

    def action_ready(self):
        for event in self.event_ids:
            event.write({'state': 'ready'})

    def action_done(self):
        if 'OUT' in self.ftp_type:
            self.action_send_file()
            for event in self.event_ids:
                event.action_done()
            self.write({'state': 'done'})
        elif 'SHIP_IN' in self.ftp_type:
            for event in self.event_ids:
                event.action_done()
            if all(event.state == 'done' for event in self.event_ids):
                self.write({'state': 'done'})
        elif 'IN' in self.ftp_type:
            if all(event.state == "done" for event in self.event_ids):
                self.write({'state': 'done'})


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    ftp_code = fields.Char('FTP Code')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    event_ids = fields.One2many('ftp.event', 'picking_id', 'Events')

    @api.depends('move_type', 'immediate_transfer', 'move_lines.state', 'move_lines.picking_id')
    def _compute_state(self):
        super(StockPicking, self)._compute_state()
        for picking in self:
            if picking.move_lines:
                if picking.picking_type_id.id == 2:
                    relevant_move_state = picking.move_lines._get_relevant_state_among_moves()
                    if relevant_move_state == 'assigned':
                        self.env['ftp.event'].create({'name': picking.name,
                                                      'picking_id': picking.id,
                                                      'ftp_type': 'SHIP_OUT'})

     #stock.picking, action_done
     #purchase.order, button_approve
     #mrp.production, action_confirm, button_mark_done


