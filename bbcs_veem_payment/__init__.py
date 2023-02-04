# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import models
from . import controllers
from . import wizard

from odoo.addons.payment import reset_payment_acquirer
import os
from veem.configuration import ConfigLoader
from veem.client.authentication import AuthenticationClient
from veem.client.requests.webhook import WebhookRequest
from veem.client.webhook import WebhookClient

def uninstall_hook(cr, registry):
    reset_payment_acquirer(cr, registry, 'veem')
    try:
        acquirers = self.env['payment.acquirer'].sudo().search([('provider','=','veem')])
        for acquirer in acquirers:
            config = ConfigLoader(yaml_file=os.getcwd()+'/%s_configuration.yaml'%str(acquirer.id))
            AuthenticationClient(config).getTokenFromClientCredentials()
           # delete a webhook
            deleteWebhookOutbound = WebhookClient(config).delete(acquirer.veem_webhook_outbound)
            deleteWebhookInbound = WebhookClient(config).delete(acquirer.veem_webhook_inbound)
    except:
        pass
