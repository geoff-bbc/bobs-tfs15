# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)



class MoveWizard(models.TransientModel):
    _name = 'veem.account.move.wizard'
    _description = 'Veem account move wizard'

    move_id = fields.Many2one(comodel_name='account.move', string='Invoice')
    move_count = fields.Integer(compute='_count_moves', store=True, compute_sudo=True)
    veem_invoice_number = fields.Char(string='Veem Reference')
    domain_move_ids = fields.Many2many(comodel_name='account.move', string='Domain Move IDs')
    email = fields.Char(related='move_id.partner_id.email', readonly=True, string='Recipient')
    amount = fields.Monetary(related='move_id.amount_residual', string='Amount', currency_field='currency_id', readonly=True)
    amount_due = fields.Monetary(string='Amount Due', currency_field='currency_id')
    amount_difference = fields.Monetary(string='Amount Difference', currency_field='currency_id')
    currency_id = fields.Many2one(related='move_id.currency_id', readonly=True)
    send_date = fields.Date(related='move_id.invoice_date', readonly=True)
    due_date = fields.Date(related='move_id.invoice_date_due', readonly=True)

    def _get_invoice_preference(self):

        INVOICE_PREFERENCE = [('default','Do not include invoice as attachment')]

        try:
            reports = self.env['ir.actions.report'].sudo().search([('binding_model_id','!=',False),('model','=','account.move')])
            for report in reports:
                INVOICE_PREFERENCE.append((report.report_name, report.name))

        except ValueError:
            return INVOICE_PREFERENCE
        
        return INVOICE_PREFERENCE
    
    def _acquirer_preference(self):
        company_ids = self.env.context.get('allowed_company_ids',[])
        acquirer = self.env['payment.acquirer'].sudo().search([('provider','=','veem'),('company_id','in', company_ids),('state','!=','disabled')], limit=1)
        if acquirer:
            return acquirer.veem_preference
        return 'default'
    
    preference = fields.Selection(_get_invoice_preference, string='Invoice PDF Format', default=_acquirer_preference)
    
    @api.depends('domain_move_ids')
    def _count_moves(self):
        print('Count Moves')
        for move in self:
            move.move_count = len(move.domain_move_ids)
        return True
    
    @api.onchange('amount')
    def onchange_amount(self):
        self.amount_due = self.amount 
    
    @api.onchange('amount_due')
    def onchange_amount_due(self):
        self.amount_difference = self.amount - self.amount_due
    
    def action_confirm(self):
        move_ids = self.env.context.get('active_ids', False)
        if move_ids:
            if len(move_ids) > 100:
                raise UserError(_('Please send Veem invoices in batches of 100 or less.'))
            moves = self.env['account.move'].browse(move_ids)
            invoices = moves.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))
            if invoices:
                invoices.send_veem_invoice(self.amount_due, self.veem_invoice_number, self.preference)
            payments = moves.filtered(lambda m: m.move_type in ('in_invoice', 'in_refund'))
            if payments:
                payments.send_veem_payment(self.amount_due, self.veem_invoice_number)
            
        return True
    

    @api.depends('move_id')
    @api.onchange('move_id')
    def _get_veem_invoice_number(self):
        move = self.move_id
        veem_invoice_number = False
        acquirer = self.env['payment.acquirer'].sudo().search([('provider','=','veem'),('company_id','=', move.company_id.id),('state','!=','disabled')], limit=1)
        if acquirer:
            # ensure that there is always a reference
            veem_invoice_number = move.name
            if acquirer.veem_reference_field == 'invoice':
                #keep as default
                veem_invoice_number = move.name
            elif acquirer.veem_reference_field == 'sales':
                order_line = self.env['sale.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                if order_line.order_id:
                    veem_invoice_number = order_line.order_id.name
                order_line = self.env['purchase.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                if order_line.order_id:
                    veem_invoice_number = order_line.order_id.name
                
            elif acquirer.veem_reference_field == 'invoice_ref':
                veem_invoice_number = move.ref or move.name
            elif acquirer.veem_reference_field == 'company_invoice':
                veem_invoice_number = move.company_id.name + ' ' + move.name
            elif acquirer.veem_reference_field == 'company_sales':
                order_line = self.env['sale.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                if order_line.order_id:
                    veem_invoice_number = move.company_id.name + ' ' + order_line.order_id.name
                order_line = self.env['purchase.order.line'].search([('invoice_lines','in',move.invoice_line_ids.ids)], limit=1)
                if order_line.order_id:
                    veem_invoice_number = order_line.order_id.name
        self.veem_invoice_number = veem_invoice_number
