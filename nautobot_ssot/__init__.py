"""App declaration for nautobot_ssot."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class NautobotSSOTAppConfig(NautobotAppConfig):
    """App configuration for the nautobot_ssot app."""

    name = "nautobot_ssot"
    verbose_name = "Single Source of Truth"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot app that enables Single Source of Truth.  Allows users to aggregate distributed data sources and/or distribute Nautobot data to other data sources such as databases and SDN controllers."
    base_url = "ssot"
    required_settings = []
    min_version = "2.0.0"
    max_version = "2.9999"
    default_settings = {
        "aci_apics": [],
        "aci_tag": "",
        "aci_tag_color": "",
        "aci_tag_up": "",
        "aci_tag_up_color": "",
        "aci_tag_down": "",
        "aci_tag_down_color": "",
        "aci_manufacturer_name": "",
        "aci_ignore_tenants": [],
        "aci_comments": "",
        "aci_site": "",
        "aristacv_apply_import_tag": False,
        "aristacv_controller_site": "",
        "aristacv_create_controller": False,
        "aristacv_cvaas_url": "www.arista.io:443",
        "aristacv_cvp_host": "",
        "aristacv_cvp_password": "",
        "aristacv_cvp_port": "443",
        "aristacv_cvp_token": "",
        "aristacv_cvp_user": "",
        "aristacv_delete_devices_on_sync": False,
        "aristacv_from_cloudvision_default_device_role": "",
        "aristacv_from_cloudvision_default_device_role_color": "",
        "aristacv_from_cloudvision_default_site": "",
        "aristacv_hostname_patterns": [],
        "aristacv_import_active": False,
        "aristacv_role_mappings": {},
        "aristacv_site_mappings": {},
        "aristacv_verify": True,
        "device42_host": "",
        "device42_username": "",
        "device42_password": "",
        "device42_defaults": {},
        "device42_delete_on_sync": False,
        "device42_use_dns": True,
        "device42_customer_is_facility": True,
        "device42_facility_prepend": "",
        "device42_role_prepend": "",
        "device42_ignore_tag": "",
        "device42_hostname_mapping": [],
        "enable_aci": False,
        "enable_aristacv": False,
        "enable_device42": False,
        "enable_infoblox": False,
        "enable_ipfabric": False,
        "enable_servicenow": False,
        "hide_example_jobs": True,
        "infoblox_default_status": "",
        "infoblox_enable_rfc1918_network_containers": False,
        "infoblox_enable_sync_to_infoblox": False,
        "infoblox_import_objects_ip_addresses": False,
        "infoblox_import_objects_subnets": False,
        "infoblox_import_objects_vlan_views": False,
        "infoblox_import_objects_vlans": False,
        "infoblox_import_subnets": [],
        "infoblox_password": "",
        "infoblox_url": "",
        "infoblox_username": "",
        "infoblox_verify_ssl": True,
        "infoblox_wapi_version": "",
        "ipfabric_api_token": "",
        "ipfabric_host": "",
        "ipfabric_ssl_verify": True,
        "ipfabric_timeout": 15,
        "ipfabric_nautobot_host": "",
        "servicenow_instance": "",
        "servicenow_password": "",
        "servicenow_username": "",
    }
    caching_config = {}

    def ready(self):
        """Trigger callback when database is ready."""
        super().ready()

config = NautobotSSOTAppConfig  # pylint:disable=invalid-name
