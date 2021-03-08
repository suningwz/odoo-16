# -*- coding: utf-8 -*-
{
    'name': "Sale Order Approval",

    'summary': """
        Sale Order Approval
        """,

    'description': """
    Sale Order Approval
    """,

    'author': "Romain Deheele",

    'category': 'sale',

    'depends': ['base', 'sale'],

    # always loaded
    'data': [
        'views/sale_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
