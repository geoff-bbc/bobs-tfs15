  
# -*- coding: utf-8 -*-

{
    'name': 'Veem Online Payments',
    'category': 'Accounting/Payment Acquirers',
    'price': 400,
    'currency': 'USD',
    'license': 'OPL-1',
    'summary': 'Easily send and receive payments via bank transfer. NO FEES within the United States and Canada.',
    'author': 'Bluebird Cloud Solutions',
    'version': '0.0.1',
    'website': 'https://www.blue-bird.cloud/solutions/odoo/veem',
    'description': 'Why lose 3% or more of your revenue by accepting credit cards or "social" payments for your invoices? Veem is the perfect platform to allow your customers to easily pay their invoices using ACH bank transfers. Want some even better news? Veem transfers and check payments within the United States and Canada are FREE!',
    'images': ['static/images/veem_payment_img1.png', 'static/images/veem_payment_img2.png', 'static/images/veem_payment_img3.png','static/images/veem_payment_img4_screenshot.png'],
    'depends': ['bbcs_pay_acquire','account'],
    'data': [
        'security/ir.model.access.csv',
        'views/payment_views.xml',
        'views/account_move_views.xml',
        'views/partner_views.xml',
        'wizard/move.xml',
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
    'application': True,
    'uninstall_hook': 'uninstall_hook'
}