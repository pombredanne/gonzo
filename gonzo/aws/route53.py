from boto.route53.connection import Route53Connection
from boto.route53.record import ResourceRecordSets
from boto.route53.exception import DNSServerError

from gonzo.config import config_proxy as config


class Route53(object):
    """ CRUD record sets on route53.
    Attempting to mask how convoluted the boto implementaton for dealing with
    R53 is at the moment """

    def __init__(
            self, zone_name=None, aws_access_key_id=None,
            aws_secret_access_key=None):

        zone_name = zone_name or config.CLOUD['DNS_ZONE']
        aws_access_key_id = aws_access_key_id or config.CLOUD[
            'AWS_ACCESS_KEY_ID']
        aws_secret_access_key = aws_secret_access_key or config.CLOUD[
            'AWS_SECRET_ACCESS_KEY']

        self.conn = Route53Connection(aws_access_key_id, aws_secret_access_key)

        self.zone = self.conn.get_hosted_zone_by_name(
            zone_name
        )["GetHostedZoneResponse"]["HostedZone"]
        self.zone_id = self.zone["Id"].split("/")[2]

    def add_remove_record(
            self, name, type, value, action="CREATE", is_qualified=False):
        """ Creates or Deletes a new record in the zone """

        if action == "DELETE" and self.is_this_master(name):
            raise Exception("You cannot remove the record of a master service")
        rrs = ResourceRecordSets(self.conn, self.zone_id)
        fqdn = name
        if not is_qualified:
            fqdn = self.fqdn(fqdn)
        change = rrs.add_change(action, fqdn, type)
        change.add_value(self.clean_value(type, value))
        try:
            rrs.commit()
        except DNSServerError as err:
            raise Exception("Can not create the DNS record - %s" % err)

    def update_record(self, name, type, new_value, old_value=None):
        """ Removes the old record and create a new one with the new value.
        If there are multiple values in the record you must specify which one
        you want to replace"""

        if not old_value:
            rec_values = self.get_values_by_name(name)
            if len(rec_values) > 1:
                raise Exception("There are multiple values for" % name)
            else:
                old_value = rec_values[0]
        self.add_remove_record(name, type, old_value, "DELETE")
        self.add_remove_record(name, type, new_value, "CREATE")

    def replace_a_record(self, ipaddress, name):
        """ replace ip address on A record """
        self.delete_dns_by_value(ipaddress)
        self.add_remove_record(name, "A", ipaddress, "CREATE")

    def delete_dns_by_value(self, value):
        """ Warning! Deletes all DNS records in the current zone
        with a matching value """
        dns_records = self.get_records_by_value(value)
        for dns_record in dns_records:
            for resource in dns_record.resource_records:
                self.add_remove_record(
                    dns_record.name, dns_record.type, resource, "DELETE",
                    is_qualified=True)

    def get_record_by_name(self, name):
        """ Gets the Record object from the zone, based on the name """
        for record in self.conn.get_all_rrsets(self.zone_id):
            if self.fqdn(name) in record.name:
                return record
        return False

    def get_records_by_value(self, value):
        """ Get a list of dns records for which the value or target matches """
        dns_records = self.conn.get_all_rrsets(self.zone_id)
        return [rec for rec in dns_records if value in rec.resource_records]

    def is_this_master(self, name):
        """ TODO - check that this isn't a master before deleting """
        return False

    def get_values_by_name(self, name):
        """ Returns the values in a named record """
        record = self.get_record_by_name(name)
        return record.resource_records  # pylint: disable=E1103

    def fqdn(self, name):
        """ Utility to turn a hostname into a FQDN """
        return "%s.%s" % (name, self.zone["Name"])

    def clean_value(self, type, value):
        """ TXT records, and probably others need values to be quoted"""
        if type == "TXT" and "\"" not in value:
            value = "\"%s\"" % value
        return value
