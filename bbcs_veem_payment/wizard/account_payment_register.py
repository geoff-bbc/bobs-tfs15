# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit= 'account.payment.register'

    def _create_payments(self):
        payments = super(AccountPaymentRegister, self)._create_payments()
        for pay in payments:
            if pay.payment_method_code == 'veem':
                pay.move_id.send_veem_payment(pay.amount, pay.ref)
        return payments