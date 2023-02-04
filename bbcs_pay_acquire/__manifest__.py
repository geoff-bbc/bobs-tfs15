    
# -*- coding: utf-8 -*-

{
    'name': 'Extended Payment Acquirers',
    'category': 'Accounting/Payment Acquirers',
    'price': 0,
    'currency': 'USD',
    'license': 'OPL-1',
    'summary': 'Framework to support the installation of additional acquirers. Requires additional purchase of specific acquirer app.',
    'author': 'Bluebird Cloud Solutions',
    'version': '0.01',
    'website': 'https://www.blue-bird.cloud/solutions/odoo/veem',
    'description': 'Framework to support the installation of additional acquirers. Requires additional purchase of specific acquirer app.',
    'depends': ['payment'],
    'data': [
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': True
}