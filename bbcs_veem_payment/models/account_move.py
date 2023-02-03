# coding: utf-8

from odoo import api, fields, models, _
from veem.exceptions import VeemException
from odoo.exceptions import UserError
from veem.models.contact_list_parameters import ContactListParameters
from veem.client.invoice import InvoiceClient
from veem.client.payment import PaymentClient
from veem.client.contact import ContactClient
from veem.client.requests.invoice import InvoiceRequest
from veem.client.requests.payment import PaymentRequest
from veem.client.requests.attachment import AttachmentRequest
from veem.client.attachment import AttachmentClient
from veem.configuration import ConfigLoader
from veem.client.authentication import AuthenticationClient

from veem.utils import deseralize
import os
import phonenumbers
import logging
import shutil


_logger = logging.getLogger(__name__)


class Move(models.Model):
    _inherit = 'account.move'

    veem_state = fields.Selection([('new','New'),('sent','Sent by Veem'),('pending', 'Pending'), ('paid', 'Paid'),('error','Veem Error')], 
                                    string='Veem Status', readonly=True, copy=False, tracking=True)
    veem_invoice_id = fields.Char(string='Veem Invoice ID', readonly=True, copy=False)
    veem_send_invoice_radio = fields.Selection(related='company_id.veem_send_invoice_radio', string='Show Send Veem Invoice button on invoices', groups='base.group_user', readonly=False)
    veem_payment_id = fields.Char(string='Veem Payment ID', readonly=True, copy=False)
    veem_reference_field = fields.Selection(related='company_id.veem_reference_field', 
                                            string='Default Reference Field', groups='base.group_user', readonly=False)
    veem_payment_request_status = fields.Selection(related='company_id.veem_payment_request_status', 
                                            string='Default status for payment request', groups='base.group_user', readonly=False)
    veem_payment_status = fields.Selection(related='company_id.veem_payment_status',
                                            string='Default status for payments', groups='base.group_user', readonly=False)
    claim_link = fields.Char(string='Claim Link', readonly=True, copy=False)

    veem_payment_full = fields.Boolean(string='Veem Payment Full', copy=False, readonly=True, tracking=False)
    #decorated field in header area
    veem_decorated_state = fields.Html(string='Veem Status',store=True, readonly=True, copy=False, compute='_compute_veem_decorated_state', compute_sudo=True)

    veem_attachment_reference = fields.Char(string='Veem Attachment Reference', readonly=True, copy=False)
    
    veem_attachment_name =  fields.Char(string='Veem Attachment Name', readonly=True, copy=False)

    # compute and search fields, in the same order of fields declaration
    @api.depends('veem_state')
    def _compute_veem_decorated_state(self):
        for record in self:
          if record.veem_state:
            message_list = {
                'sent':'Sent via Veem, Waiting for Payment',
                'error':'Veem Error',
                'paid':'Marked Paid in Veem',
                'new':'New',
                'pending':'Pending'
              }
            status_msg = message_list[record.veem_state]
            record['veem_decorated_state']= '<span style="font-size:13px;"><a href="https://apps.veem.com/CustomerApp/Dashboard" target="_blank"><img alt="Open Veem.com in a new window" style="margin-right:4px;" src="/bbcs_veem_payment/static/src/img/veem_v_20.png"></a>'+status_msg+'</span>'
          else:
            record['veem_decorated_state']='not connected to Veem'
            
    # def _post(self, soft=True):
    #     # Send veem payment.
    #     for pay in self.payment_id:
    #         if pay.payment_method_code == 'veem':
    #             self.send_veem_payment(pay.amount, pay.ref)
    #     return super()._post(soft)
    
    def action_process_veem_invoice(self):
        return {
            'name': _('Process Veem Invoice'),
            'view_mode': 'form',
            'res_model': 'veem.account.move.wizard',
            'view_id': self.env.ref('bbcs_veem_payment.view_veem_account_move').id,
            'type': 'ir.actions.act_window',
            'context': {'default_move_id': self.id, 'default_domain_move_ids':[(6, 0,self.ids)], 'default_preference': self.company_id.veem_preference},
            'target': 'new'
        }
    
    # def action_process_veem_payment(self):
    #     return {
    #         'name': _('Process Veem Payment'),
    #         'view_mode': 'form',
    #         'res_model': 'veem.account.move.wizard',
    #         'view_id': self.env.ref('bbcs_veem_payment.view_veem_account_move').id,
    #         'type': 'ir.actions.act_window',
    #         'context': {'default_move_id': self.id, 'default_domain_move_ids':[(6, 0,self.ids)]},
    #         'target': 'new'
    #     }
    
    def send_veem_invoice(self, amount_due=0, send_veem_invoice=False, preference=None):
        _logger.info('Sending Veem Invoice')
        for move in self:
            if (move.veem_state != False and move.veem_state != 'error') or move.state != 'posted':
                _logger.info('Ignored move id %s because veem invoice is already processed!'%move.id)
                continue
            acquirer = self.env['payment.acquirer'].sudo().search([('provider','=','veem'),('company_id','=', move.company_id.id),('state','!=','disabled')], limit=1)
            # _logger.info('Acquirer %s'%acquirer.name)
            if acquirer:
                try:
                    # _logger.info(os.getcwd()+'/%s_configuration.yaml'%str(acquirer.id))
                    config = ConfigLoader(yaml_file=os.getcwd()+'/%s_configuration.yaml'%str(acquirer.id))
                    # _logger.info('Config %s'%config)
                    AuthenticationClient(config).getTokenFromClientCredentials()
                    # tokenResponse = AuthenticationClient(config).refreshToken(acquirer.veem_refresh_token)
                    # #_logger.info('TokenResponse %s'%tokenResponse)
                    # acquirer.write({'veem_refresh_token':tokenResponse.refreshToken})
                except:
                    raise UserError(_('Go to Veem Payment Acquirer and Reconnect!'))
                
            # # print(config.client_id, config.client_secret)
            # # login to Veem server with client credentials
            # tokenResponse = AuthenticationClient(config).getTokenFromAuthorizationCode()
            # print(tokenResponse, 'Here testign')
            if acquirer:
                try:
                    first_name = None
                    last_name = None
                    business_name = None
                    reference = None
                    order_id = False

                    attachments = []

                    amount = amount_due or move.amount_residual or 0.0
                    if amount < 10.0:
                        raise UserError(_('Veem requires amount to be greater than 10.00.'))
                    
                    if preference != 'default':
                        report = self.env['ir.actions.report'].sudo().search([('binding_model_id','!=',False),('model','=','account.move')], limit=1)
                        if report:
                            report._render([move.id])
                            attachment = self.env['ir.attachment'].search([('res_id','=',move.id),('res_model','=','account.move')], limit=1)
                            if attachment:
                                full_path = attachment._full_path(attachment.store_fname)
                                shutil.copyfile(full_path, '/tmp/%s'%attachment.name)
                                attachment_client = AttachmentClient(config).upload(
                                    dict(path='/tmp/%s'%attachment.name),attachment.name)
                                attachment_request = AttachmentRequest(type='ExternalInvoice',
                                                                    name=attachment_client.name, 
                                                                    referenceId=attachment_client.referenceId)
                                attachments.append(attachment_request)
                                move.write({'veem_attachment_reference':attachment_client.referenceId, 'veem_attachment_name':attachment_client.name})
                    
                    if move.partner_id.name and (move.partner_id.phone or move.partner_id.mobile) and move.partner_id.country_id:
                        if (move.partner_id.is_company==False and move.partner_id.parent_id==False):
                            veem_type = 'Personal'
                            temp_name = move.partner_id.name.split()
                            first_name = temp_name[0]
                            last_name = ' '.join(l for l in temp_name[1:])
                            business_name = move.partner_id.name
                        elif (move.partner_id.parent_id):
                            veem_type = 'Business'
                            temp_name = move.partner_id.name.split()
                            first_name = temp_name[0]
                            last_name = ' '.join(l for l in temp_name[1:])
                            business_name = move.partner_id.parent_id.name
                        else:
                            veem_type = 'Business'
                            first_name = 'Billing'
                            last_name = 'Department'
                            business_name = move.partner_id.name
                        phone = phonenumbers.parse(move.partner_id.phone or move.partner_id.mobile)
                        if not phone.country_code:
                            raise UserError(_('Veem requires the phone number to be correctly formatted, including a country code. Please update the contact and try again.'))
                        due_date = str(move.invoice_date_due) + 'T23:00:00.000Z' if move.invoice_date_due else None
                        # ensure that there is always a reference
                        reference = move.name
                        if acquirer.veem_reference_field == 'invoice':
                            #keep as default
                            reference = move.name
                        elif acquirer.veem_reference_field == 'sales':
                            order_line = self.env['sale.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                            if order_line.order_id:
                                reference = order_line.order_id.name or move.name
                        elif acquirer.veem_reference_field == 'invoice_ref':
                            reference = move.ref or move.name
                        elif acquirer.veem_reference_field == 'company_invoice':
                            reference = move.company_id.name + ' ' + move.name
                        elif acquirer.veem_reference_field == 'company_sales':
                            order_line = self.env['sale.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                            if order_line.order_id:
                                reference = move.company_id.name + ' ' + order_line.order_id.name or move.name

                        # define an InvoiceRequest
                        invoice = InvoiceRequest(payer=dict(type=veem_type or None,
                                                            email=move.partner_id.email or None,
                                                            firstName=first_name or None,
                                                            lastName=last_name or None,
                                                            businessName=business_name or None,
                                                            countryCode=move.partner_id.country_id.code or None,
                                                            phoneCountryCode=phone.country_code or None,
                                                            phone=phone.national_number or None),
                            amount=dict(number=amount_due or move.amount_residual or 0.0, currency=move.currency_id.name  or None),
                            externalInvoiceRefId=send_veem_invoice or reference or None,
                            # notes=move.narration or None, ## Holding off on this mapping for now
                            dueDate=due_date  or None,
                            attachments=attachments)
                        
                        # create an invoice
                        sendInvoice = InvoiceClient(config).create(invoice)
                        if acquirer.veem_payment_request_status == 'send':
                            InvoiceClient(config).send(sendInvoice.id)
                        # _logger.info('SendInvoice %s'%sendInvoice)
                        # print(sendInvoice.payer, sendInvoice.payer.id)
                        move.write({'veem_invoice_id':sendInvoice.id, 'veem_state':'sent','claim_link':sendInvoice.claimLink})

                        # print(sendInvoice, sendInvoice.status)

                        # get customer
                        if not move.partner_id.veem_id:
                            contact_list = ContactListParameters(email=move.partner_id.email, pageSize=1, batchItemIds=[])                        
                            customers = ContactClient(config).list(contact_list)
                            # print(customers.size, customers.number, customers.numberOfElements, customers.totalElements)
                            for i in range(0, customers.totalElements):
                                move.partner_id.veem_id = customers.content[i].id
                        
                        tx = self.env['payment.transaction'].create({
                                'amount': amount_due or move.amount_residual,
                                'acquirer_id': acquirer.id,
                                'currency_id': move.currency_id.id,
                                'reference': sendInvoice.id,
                                'partner_id': move.partner_id.id,
                                'invoice_ids': [(6, 0, [move.id])]})
                        
                        if amount_due == move.amount_residual:
                            move.veem_payment_full = True

                    else:
                        raise UserError(_('Veem requires email, phone and country to be specified on the contact.'))


                except Exception as e:
                    move.veem_state = 'error'
                    move.env.cr.commit()
                    try:
                        message = e.message
                    except:
                        message = e
                    raise UserError(_('Veem Error: %s'%e))
        return True

    def send_veem_payment(self, amount_due=0, send_veem_invoice=False):
        _logger.info('Sending Veem Payment with amount %s and transaction reference %s'%(amount_due, send_veem_invoice))
        for move in self:
            if (move.veem_state != False and move.veem_state != 'error'):
                _logger.info('Ignored move id %s because Veem payment is already processed.'%move.id)
                continue
            acquirer = self.env['payment.acquirer'].sudo().search([('provider','=','veem'),('company_id','=', move.company_id.id),('state','!=','disabled')], limit=1)
            if acquirer:
                try:
                    #_logger.info('Acquirer %s'%acquirer.name)
                    config = ConfigLoader(yaml_file=os.getcwd()+'/%s_configuration.yaml'%str(acquirer.id))
                    AuthenticationClient(config).getTokenFromClientCredentials()
                    # #_logger.info('Config %s'%config)
                    # tokenResponse = AuthenticationClient(config).refreshToken(acquirer.veem_refresh_token)
                    # #_logger.info('TokenResponse %s'%tokenResponse)
                    # acquirer.write({'veem_refresh_token':tokenResponse.refreshToken})
                
                except:
                    raise UserError(_('Go to Veem Payment Acquirer and Reconnect!'))

            if acquirer:
                try:
                    first_name = None
                    last_name = None
                    business_name = None
                    reference = None
                    order_id = False
                    amount = amount_due or move.amount_residual or 0.0
                    if amount < 10.0:
                        raise UserError(_('Veem requires amount to be greater than 10.00.'))
                    
                    if move.partner_id.name and (move.partner_id.phone or move.partner_id.mobile) and move.partner_id.country_id:
                        if (move.partner_id.is_company==False and move.partner_id.parent_id==False):
                            veem_type = 'Personal'
                            temp_name = move.partner_id.name.split()
                            first_name = temp_name[0]
                            last_name = ' '.join(l for l in temp_name[1:])
                            business_name = move.partner_id.name
                        elif (move.partner_id.parent_id):
                            veem_type = 'Business'
                            temp_name = move.partner_id.name.split()
                            first_name = temp_name[0]
                            last_name = ' '.join(l for l in temp_name[1:])
                            business_name = move.partner_id.parent_id.name
                        else:
                            veem_type = 'Business'
                            first_name = 'Billing'
                            last_name = 'Department'
                            business_name = move.partner_id.name
                        phone = phonenumbers.parse(move.partner_id.phone or move.partner_id.mobile)
                        if not phone.country_code:
                            raise UserError(_('Veem requires the phone number to be correctly formatted, including a country code. Please update the contact and try again.'))
                        due_date = str(move.invoice_date_due) + 'T23:00:00.000Z' if move.invoice_date_due else None
                        # ensure that there is always a reference
                        reference = move.name
                        if acquirer.veem_reference_field == 'invoice':
                            #keep as default
                            reference = move.name
                        elif acquirer.veem_reference_field == 'sales':
                            order_line = self.env['purchase.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                            if order_line.order_id:
                                reference = order_line.order_id.name or move.name
                        elif acquirer.veem_reference_field == 'invoice_ref':
                            reference = move.ref or move.name
                        elif acquirer.veem_reference_field == 'company_invoice':
                            reference = move.company_id.name + ' ' + move.name
                        elif acquirer.veem_reference_field == 'company_sales':
                            order_line = self.env['purchase.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                            if order_line.order_id:
                                reference = move.company_id.name + ' ' + order_line.order_id.name or move.name

                        # define an PaymentRequest
                        payment = PaymentRequest(payee=dict(type=veem_type or None,
                                                            email=move.partner_id.email or None,
                                                            firstName=first_name or None,
                                                            lastName=last_name or None,
                                                            businessName=business_name or None,
                                                            countryCode=move.partner_id.country_id.code or None,
                                                            phoneCountryCode=phone.country_code or None,
                                                            phone=phone.national_number or None),
                            amount=dict(number=amount_due or move.amount_residual, currency=move.currency_id.name or None),
                            externalInvoiceRefId=send_veem_invoice or reference or None,
                            #notes=move.narration or None, ## Holding off on this mapping for now
                            dueDate=due_date or None)
                        
                        # create a payment
                        sendPayment = PaymentClient(config).create(payment)
                        if acquirer.veem_payment_status == 'send':
                            PaymentClient(config).send(sendPayment.id)
                        _logger.info('SendPayment %s'%sendPayment)
                        move.write({'veem_payment_id':sendPayment.id, 'veem_state':'sent','claim_link':sendPayment.claimLink})

                        # get customer
                        if not move.partner_id.veem_id:
                            contact_list = ContactListParameters(email=move.partner_id.email, pageSize=1, batchItemIds=[])                        
                            customers = ContactClient(config).list(contact_list)
                            for i in range(0, customers.totalElements):
                                move.partner_id.veem_id = customers.content[i].id
                        
                        # tx = self.env['payment.transaction'].create({
                        #         'amount': amount_due or move.amount_residual,
                        #         'acquirer_id': acquirer.id,
                        #         'currency_id': move.currency_id.id,
                        #         'reference': sendPayment.id,
                        #         'partner_id': move.partner_id.id,
                        #         'invoice_ids': [(6, 0, [move.id])]})
                        
                        if amount_due == move.amount_residual:
                            move.veem_payment_full = True
                    else:
                        raise UserError(_('Veem requires email, phone and country to be specified on the contact.'))


                except Exception as e:
                    move.veem_state = 'error'
                    move.env.cr.commit()
                    try:
                        message = e.message
                    except:
                        message = e
                    raise UserError(_('Veem Error: %s'%e))
        return True