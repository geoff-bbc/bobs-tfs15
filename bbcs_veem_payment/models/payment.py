# coding: utf-8

import logging
import json

from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.bbcs_veem_payment.controllers.main import VeemController
from odoo.exceptions import UserError
import yaml
import os
from veem.configuration import ConfigLoader
from veem.client.authentication import AuthenticationClient
from veem.client.requests.webhook import WebhookRequest
from veem.client.webhook import WebhookClient


_logger = logging.getLogger(__name__)



class AcquirerVeem(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[
        ('veem', 'Veem')
    ], ondelete={'veem': 'set default'})

    veem_client_id = fields.Char('Client ID', required_if_provider='veem', groups='base.group_user')
    veem_client_secret = fields.Char('Client Secret', required_if_provider='veem', groups='base.group_user')
    veem_webhook_outbound = fields.Char(string='Webhook Outbound ID', groups='base.group_user')
    veem_webhook_inbound = fields.Char(string='Webhook Inbound ID', groups='base.group_user')
    veem_url = fields.Char('URL', required_if_provider='veem', groups='base.group_user', default="https://sandbox-api.veem.com/")
    veem_authorization_code = fields.Char('Authorization Code', groups='base.group_user', readonly=True)
    veem_redirect_url = fields.Char('Redirect URL', required_if_provider='veem', compute='_get_veem_redirect_url', groups='base.group_user')
    veem_config_path = fields.Char('Config Path', groups='base.group_user', readonly=True)

    veem_send_invoice_radio = fields.Selection(related='company_id.veem_send_invoice_radio', string='Show Send Veem Invoice button on invoices', groups='base.group_user', readonly=False)
    veem_reference_field = fields.Selection(related='company_id.veem_reference_field', 
                                            string='Default Reference Field', groups='base.group_user', required_if_provider='veem', readonly=False)
    veem_payment_request_status = fields.Selection(related='company_id.veem_payment_request_status', 
                                            string='Default status for payment request', groups='base.group_user', readonly=False)
    veem_payment_status = fields.Selection(related='company_id.veem_payment_status',
                                            string='Default status for payments', groups='base.group_user', required_if_provider='veem', readonly=False)
    
    veem_refresh_token = fields.Char(related='company_id.veem_refresh_token', string='Refresh Token', groups='base.group_user', readonly=False)
    
    veem_preference = fields.Selection(related='company_id.veem_preference', string='Preferred Invoice Print Format', required_if_provider='veem', default='default', groups='base.group_user', readonly=False)


    @api.onchange('veem_client_id', 'veem_client_secret', 'veem_url', 'veem_authorization_code', 'veem_redirect_url', 'state')
    def configurateYAML(self):
        environment = 'prod' if self.state == 'enabled' else 'test'
        if environment == 'prod':
            self.veem_url = 'https://api.veem.com/'
        else:
            self.veem_url = 'https://sandbox-api.veem.com/'
        
        dict_file = {'client_id': self.veem_client_id, 'client_secret': self.veem_client_secret, 'url': self.veem_url, 
                        'authorizationCode': self.veem_authorization_code, 'redirectUrl': self.veem_redirect_url}
        
        path = os.getcwd()+'/%s_configuration.yaml'%str(self._origin.id)
        with open(path, 'w') as file:
            documents = yaml.dump(dict_file, file)
        self.veem_config_path = path
        _logger.info(_('Veem Configuration Changed on path %s'%path))
    
    def connect_veem(self):
        try:
            config = ConfigLoader(yaml_file=os.getcwd()+'/%s_configuration.yaml'%str(self.id))
            AuthenticationClient(config).getTokenFromClientCredentials()
            web_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

            # define an WebhookRequest
            webhook_outbound = WebhookRequest(event='OUTBOUND_PAYMENT_STATUS_UPDATED',callbackURL='%s/veem/payment/status'%(web_base_url))
            webhook_inbound = WebhookRequest(event='INBOUND_PAYMENT_STATUS_UPDATED',callbackURL='%s/veem/payment/status'%(web_base_url))
            # create a webhook
            sendWebhookOutbound = WebhookClient(config).create(webhook_outbound)
            sendWebhookInbound = WebhookClient(config).create(webhook_inbound)

            if sendWebhookInbound:
                self.veem_webhook_inbound = sendWebhookInbound.id
            if sendWebhookOutbound:
                self.veem_webhook_outbound = sendWebhookOutbound.id
        except:
            raise UserError(_('Go to Veem Payment Acquirer and Reconnect!'))
        # return {
        #     'url': '/veem/authorize/%s'%self.id,
        #     'type': 'ir.actions.act_url',
        #     'target': 'self'
        # }
        title = _("Veem Connection Test Succeeded!")
        message = _("Everything seems properly set up!")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'sticky': False,
            }
        }



    def _get_veem_authorize_url(self):
        web_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        url = 'https://sandbox-api.veem.com/oauth/authorize?client_id=%s&redirect_uri=%s/veem/%s/oauth/code_callback&response_type=code'%(self.veem_client_id, web_base_url, self.id)
        #acquirer.veem_url = url
        return url
    
    def _get_veem_redirect_url(self):
        web_base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for acquirer in self:
            url = '%s/veem/%s/oauth/code_callback'%(web_base_url, acquirer.id)
            acquirer.veem_redirect_url = url

        


class TxVeem(models.Model):
    _inherit = 'payment.transaction'

    status_field = fields.Char(string='Veem Status')
    veem_txn_type = fields.Char(string='Veem Transaction Type')


    def process_veem_transaction(self, type_data, data):
        former_tx_state = self.state
        res = dict()
        if type_data.get('type') == 'PAYMENT_STATUS_UPDATED':
            res['veem_txn_type'] = type_data.get('type')
        res['acquirer_reference'] = data.get('id')
        if data.get('status') == 'Drafted':
            self.write({'state':'draft'})
        if data.get('status') == 'Sent':
            self._set_transaction_pending()
        if data.get('status') == 'Claimed':
            self._set_transaction_pending()
        if data.get('status') == 'PendingAuth':
            self._set_transaction_pending()
        if data.get('status') == 'Authorized':
            self._set_transaction_authorized()
        if data.get('status') == 'InProgress':
            self._set_transaction_authorized()
        if data.get('status') == 'Complete':
            self._set_transaction_done()
            self.invoice_ids.write({'veem_state':'paid'})
            self._post_process_after_done()
        if data.get('status') == 'Cancelled':
            self._set_transaction_cancel()
        if data.get('status') == 'Closed':
            self._set_transaction_error()
        self.write(res)
    

