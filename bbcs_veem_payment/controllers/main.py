# -*- coding: utf-8 -*-

import json
import logging
import pprint

import requests
import werkzeug
from werkzeug import urls
from werkzeug.urls import url_encode

from odoo import http
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request

import os
from veem.configuration import ConfigLoader
from veem.client.authentication import AuthenticationClient

_logger = logging.getLogger(__name__)


class VeemController(http.Controller):

    @http.route(['/veem/authorize/<int:acquirer_id>'], type='http', auth='user', methods=['GET'])
    def veem_login(self, acquirer_id, **kw):
        acquirer = request.env['payment.acquirer'].sudo().browse(acquirer_id)
        response = werkzeug.utils.redirect(acquirer._get_veem_authorize_url())
        return response
    
    @http.route(['/veem/<int:acquirer_id>/oauth/code_callback'], type='http', auth='user', methods=['GET'])
    def veem_authorization_code(self, acquirer_id, **kw):
        try:
            if 'code' in kw:
                authorization_code = kw.get('code', False)
                acquirer = request.env['payment.acquirer'].sudo().browse(acquirer_id)
                acquirer.write({'veem_authorization_code':authorization_code})
                acquirer.configurateYAML()
                config = ConfigLoader(yaml_file=os.getcwd()+'/%s_configuration.yaml'%str(acquirer.id))
                AuthenticationClient(config).getTokenFromClientCredentials()
                
                # tokenResponse = AuthenticationClient(config).getTokenFromAuthorizationCode()
                # print(tokenResponse, 'Here testing')
                
                # acquirer.write({'veem_refresh_token':tokenResponse.get('refresh_token', False)})
                
            web_base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
            response = werkzeug.utils.redirect(web_base_url)
            url_params = {
                'action': request.env.ref('payment.action_payment_acquirer').id,
                'view_type': 'form',
                'model': 'payment.acquirer',
                'id': acquirer_id
            }

            return werkzeug.utils.redirect('/web?#%s' % url_encode(url_params))
        except Exception as e:
            return request.not_found()
    

    @http.route(['/veem/payment/status'], type='http', auth="public", website=True, methods=['POST'], csrf=False)
    def veem_payment_status(self, **post):
        veem_url = request.httprequest.url
        _logger.info('Veem URL %s'%veem_url)
        data = json.loads(request.httprequest.data)
        #_logger.info('Data %s', data)
        if 'type' in data and data.get('type') == 'PAYMENT_STATUS_UPDATED':
            transaction_data = json.loads(data.get('data', dict()))
            if transaction_data.get('invoiceId'):
                #invoice
                tx = request.env['payment.transaction'].sudo().search([('reference','=',str(transaction_data.get('invoiceId')))], limit=1)
                acquirer = self.env['payment.acquirer'].sudo().search([('provider','=','veem'),('company_id','=', tx.company_id.id),('state','!=','disabled')], limit=1)
                if acquirer and ((acquirer.state == 'test' and 'sandbox' in veem_url) or (acquirer.state == 'enabled' and 'sandbox' not in veem_url)):
                    states = (transaction_data.get('invoiceId'), transaction_data.get('status'), tx.state)
                    if tx and transaction_data.get('status'):
                        _logger.info('Notification from Veem invoice for the reference %s: received %s, state is %s', states)
                        tx.sudo().process_veem_transaction(data, transaction_data)
                    else:
                        _logger.warning('Notification from Veem invoice for the reference %s: received %s but state is %s', states)
            elif transaction_data.get('id'):
                #payment
                bill = request.env['account.move'].sudo().search([('veem_invoice_id','=',str(transaction_data.get('id')))], limit=1)
                acquirer = self.env['payment.acquirer'].sudo().search([('provider','=','veem'),('company_id','=', tx.company_id.id),('state','!=','disabled')], limit=1)
                if acquirer and ((acquirer.state == 'test' and 'sandbox' in veem_url) or (acquirer.state == 'enabled' and 'sandbox' not in veem_url)):
                    states = (transaction_data.get('id'), transaction_data.get('status'), bill.state)
                    if bill and transaction_data.get('status'):
                        _logger.info('Notification from Veem payment for the reference %s: received %s, state is %s', states)
                        if transaction_data.get('status') == 'Complete':
                            bill.write({'veem_state':'paid'})
                    else:
                        _logger.warning('Notification from Veem payment for the reference %s: received %s but state is %s', states)

        return '[accepted]'



          