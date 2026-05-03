{
    'name': "Odoo API REST",
    'summary': """
        Odoo REST API""",
    'description': """
        Odoo API REST for developers to create, read, update and delete records from Odoo using REST API.
    """,
    'author': "Yezileli Ilomo",
    'website': "https://github.com/yezyilomo/odoo-rest-api",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'developers',
    'version': '17.0.1.3.0',

    # License
    'license': "Other proprietary",

    # Dependencies
    'depends': ['base'],

    "application": True,
    "installable": True,
    "auto_install": False,

    'external_dependencies': {
        'python': ['pypeg2']
    }
}
