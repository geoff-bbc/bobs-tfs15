# coding: utf-8

from odoo import api, fields, models, _

class Partner(models.Model):
    _inherit = 'res.partner'

    veem_id = fields.Char('Veem ID', readonly=True, copy=False)