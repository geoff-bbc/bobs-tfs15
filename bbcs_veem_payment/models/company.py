# coding: utf-8

from odoo import api, fields, models, _

class Company(models.Model):
    _inherit = 'res.company'

    veem_send_invoice_radio = fields.Selection([('yes','yes'),('no','no')],'Show Send Veem Invoice button on invoices', default='yes', groups='base.group_user', help='Set to no if your organization only wants to send payments via Veem.')
    veem_reference_field = fields.Selection([('invoice','Invoice Name'),('sales','Sales Order Name'),('invoice_ref','Customer Reference on Invoice'),\
                                            ('company_invoice','Company + Invoice  Name'),('company_sales','Company + Sales Order Name')], 
                                            'Default Reference Field', groups='base.group_user', help='Sets the default Veem Reference based on the transaction properties. If the property is not set then the transaction name will be used by default.')
    veem_payment_request_status = fields.Selection([('send','Immediately send to customer'),('draft','Draft would need to be sent from Veem')], 
                                            'Default status for payment request', groups='base.group_user')
    veem_payment_status = fields.Selection([('send','Immediately send to recipient'),('draft','Draft - needs to be sent from Veem')], 
                                            'Default status for payments', groups='base.group_user')
    veem_refresh_token = fields.Char(string='Refresh Token', groups='base.group_user')

    
    def _get_invoice_preference(self):

        INVOICE_PREFERENCE = [('default','Do not include invoice as attachment')]

        try:
            reports = self.env['ir.actions.report'].sudo().search([('binding_model_id','!=',False),('model','=','account.move')])
            for report in reports:
                INVOICE_PREFERENCE.append((report.report_name, report.name))

        except ValueError:
            return INVOICE_PREFERENCE
        
        return INVOICE_PREFERENCE
    
    veem_preference = fields.Selection(_get_invoice_preference, string='Preferred Invoice Print Format', groups='base.group_user')


    

