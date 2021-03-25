# Copyright 2021 Romain Deheele
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "FTP Spidy",
    "summary": "FTP Spidy",
    "version": "13.0.1.0.0",
    "author": "Romain Deheele",
    "category": "Warehouse",
    "license": "AGPL-3",
    "depends": ["stock", "sale", "delivery"],
    "data": ['views/spidy_views.xml',
             'data/spidy_cron.xml',
             'security/ir.model.access.csv'
    ],
    "installable": True,
    "auto_install": False,
}
