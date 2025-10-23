import frappe

from nano_press.nano_press.doctype.server.server import Server


def get_context(context):
	context.public_key = Server._read_local_public_key()
	return context
