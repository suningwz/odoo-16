# Copyright 2021 Romain Deheele
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import io, csv
import base64
from datetime import datetime
import pytz
from dateutil.relativedelta import relativedelta
from odoo import fields, models, api


class FtpBackend(models.Model):
    _name = 'ftp.backend'

    name = fields.Char('FTP Backend')
    host = fields.Char('URL')
    port = fields.Integer('Port')
    username = fields.Char('Username')
    password = fields.Char('Password')


class FtpEvent(models.Model):
    _name = "ftp.event"

    def _compute_name(self):
        for event in self:
            if event.picking_id:
                event.name = event.picking_id.name
            else:
                event.name = ''

    name = fields.Char('Name', compute='_compute_name')
    ftp_type = fields.Selection([('SHIP_OUT', 'SHIP_OUT'), ('REC_OUT', 'REC_OUT')], 'Type')
    state = fields.Selection([('draft', 'Draft'), ('ready', 'Ready'), ('done', 'Done')], 'State', default='draft')
    job_id = fields.Many2one('ftp.job', 'Job')
    picking_id = fields.Many2one('stock.picking', 'Picking')

    def action_done(self):
        self.write({'state': 'done'})

    def execute_ready_in_events(self):
        ready_in_events = self.search([('ftp_type','like','%IN'), ('state','=','ready')])
        for event in ready_in_events:
            event.action_done()
        return True


class FtpJob(models.Model):
    _name = "ftp.job"
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    def _compute_name(self):
        for job in self:
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
                              ('done', 'Done')], 'State')
    event_ids = fields.One2many('ftp.event', 'job_id', 'Events')

    def _scheduler_ftp_import_in_files(self):
        #self.action_receive_files('/IN/RES/CR_PRE/', 'SHIP_IN')
        #self.action_receive_files('/IN/RES/CR_REC/', 'REC_IN')
        #self.action_receive_files('/IN/RES/CR_MVT/', 'MVT_IN')
        return True

    def _scheduler_ftp_export_products(self):
        self.create({'ftp_type': 'PRODUCT_OUT', 'state': 'progress'})

    def _scheduler_ftp_export_barcodes(self):
        self.create({'ftp_type': 'BARCODE_OUT', 'state': 'progress'})

    def _set_datetime_job(self, ftp_type, interval_number):
        now = fields.Datetime.now()
        from_datetime = now - relativedelta(minutes=interval_number)
        self.create({'ftp_type': ftp_type,
                     'from_datetime': from_datetime,
                     'to_datetime': now,
                     'state': 'draft'})

    def _scheduler_ftp_export_shipping(self, interval_number):
        self._set_datetime_job('SHIP_OUT', interval_number)

    def _scheduler_ftp_export_receiving(self, interval_numer):
        self._set_datetime_job('REC_OUT')

    def parse_attachment_and_create_events(self):
        return True

    def action_plan(self):
        if 'OUT' in self.ftp_type:
            #add events
            event_ids = self.env['ftp.event'].search([('ftp_type', '=', self.ftp_type),
                                                      ('create_date', '<=', self.to_datetime),
                                                      ('create_date', '>=', self.from_datetime),
                                                      ('job_id','=', False)])
            if event_ids:
                event_ids.write({'job_id': self.id})
                self.write({'state': 'progress'})
            else:
                self.write({'state': 'done'})
        if 'IN' in self.ftp_type:
            self.parse_attachment_and_create_events()
            self.write({'state': 'progress'})

    def _prepare_barcode_out_datas(self):
        datas = []
        datas.append(['Société/company', 'Entrepôt/warehouse', 'Réservé Spidy/Spidy reserved',
                      'Client propriétaire/owner code', 'Code produit/product code', 'Code à barre/Barcode',
                      'Quantité/quantity', 'Code unité/Unit code', 'Adresse email erreurs/Errors email adress'])
        products = self.env['product.product'].search([('sale_ok', '=', True)])
        for product in products:
            datas.append(['ASF', 'ATS', '', 'RES', product.default_code, product.barcode, '', '', 'si@projet-resilience.fr'])
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
                      'Réservé spidy', 'Réservé spidy', 'email erreur'])
        products = self.env['product.product'].search([('sale_ok', '=', True)])
        for product in products:
            datas.append(['ASF', 'ATS', '', 'RES', product.default_code, '', product.name, '', '', '', 'UN', 'Unité', 1,
                          '', '', '', '', '', '', 1, product.weight, '', '', '', '', '', product.list_price, 1,
                          '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '',
                          '', '', '', 3, '', 'AT', '', '', '', 'si@projet-resilience.fr'])
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
                datas.append(['', 'ASF', 'LVD', sale.name, 'RES', partner.name or '', partner.street or '', partner.street2 or '', '',
                              partner.zip or '', partner.city or '', partner.country_id and partner.country_id.code or '',
                              '', '', '', '', '', 1, pick.scheduled_date and (pick.scheduled_date.strftime('%y%m%d')) or '',
                              '', '', '', '', '', '', '', '', '', '', '', '',
                              line_nb, line.product_id and line.product_id.default_code or '', '', int(line.product_uom_qty) or '', '', '', line.price_unit or '',
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
            content = base64.encodebytes(f.getvalue().encode('utf-8'))
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

    def ftp_connect(self):
        backend = self.env['ftp.backend'].search([],limit=1)
        import pdb;pdb.set_trace()
        from ftplib import FTP
        ftp = FTP(backend.host)
        ftp.login(user=backend.username, passwd=backend.password)
        return ftp

    def action_receive_files(self, remote_path, ftp_type):
        import base64
        ftp = self.ftp_connect()
        ftp.cwd(remote_path)
        #remote_path = '/IN/RES/CR_PRE/'
        local_path = '/tmp/'
        #files = []
        filenames = ftp.nlst()
        for filename in filenames:
            file = open('/tmp/' + filename, 'wb')
            ftp.retrbinary('RETR ' + filename, file.write, 1024)
            file.close()
        ftp.quit()
        for filename in filenames:
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
        return True

    """for filename in sftp.listdir(remote_path):
            if fnmatch.fnmatch(filename, "*.CSV"):
                files.append(filename)
        for file in files:
            file_remote = remote_path + file
            file_local = local_path + file

            print(file_remote + '>>>' + file_local)

            sftp.get(file_remote, file_local)

            fichier = open(file_local, 'r')
            fichier_string = fichier.read()
            fichier_base64 = base64.encodestring(fichier_string)
            fichier.close()
            now = fields.Datetime.now()
            ftp_type = 'SHIP_IN' # TODO: reprendre qd acces au FTP IN
            job_id = self.create({'ftp_type': ftp_type,
                                  'to_datetime': now,
                                  'state': 'draft'})
            attachment = self.env['ir.attachment'].create({
                'datas': fichier_base64,
                'name': file,
                'type': 'binary',
                'res_id': job_id,
                'res_model': 'ftp.job'
            })
        sftp.close()
        ssh.close()"""

    def action_send_file(self):
        ssh, sftp = self.ftp_connect()
        attachment = self.env['ir.attachment'].search([('res_model','=','ftp.job'),
                                                       ('res_id','=',self.id)],
                                                      order='id desc', limit=1)
        filename = attachment.name
        remote_path = '/uploads/' + filename
        local_path = '/tmp/' + filename
        test = sftp.put(localpath, path)
        sftp.close()
        ssh.close()

    def action_ready(self):
        for event in self.event_ids:
            event.write({'state': 'ready'})

    def action_done(self):
        if 'OUT' in self.ftp_type:
            #self.action_send_file()
            for event in self.event_ids:
                event.action_done()
            self.write({'state': 'done'})
        if 'IN' in self.ftp_type:
            if all(event.state == "done" for event in self.event_ids):
                self.write({'state': 'done'})


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    event_ids = fields.One2many('ftp.event', 'picking_id', 'Events')

    #teste: ok
    def action_assign(self):
        super(StockPicking, self).action_assign()
        if self.picking_type_id.id == 2 and self.state == 'assigned':
            self.env['ftp.event'].create({'name': self.name,
                                          'picking_id': self.id,
                                          'ftp_type': 'SHIP_OUT'})

     #stock.picking, action_done
     #purchase.order, button_approve
     #mrp.production, action_confirm, button_mark_done
