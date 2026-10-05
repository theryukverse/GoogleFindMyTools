#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import datetime


class WrappedLocation:
    def __init__(self, decrypted_location, time, accuracy, status, is_own_report, name):
        self.time = time
        self.status = status
        self.decrypted_location = decrypted_location
        self.is_own_report = is_own_report
        self.accuracy = accuracy
        self.name = name

    def get_parsed_location(self):
        """Attempts to parse the decrypted_location protobuf bytes into a Location object."""
        if not self.decrypted_location:
            return None
        try:
            from ProtoDecoders import DeviceUpdate_pb2
            proto_loc = DeviceUpdate_pb2.Location()
            proto_loc.ParseFromString(self.decrypted_location)
            return proto_loc
        except Exception:
            return None

    @property
    def latitude(self):
        proto_loc = self.get_parsed_location()
        if proto_loc is not None:
            return proto_loc.latitude / 1e7
        return None

    @property
    def longitude(self):
        proto_loc = self.get_parsed_location()
        if proto_loc is not None:
            return proto_loc.longitude / 1e7
        return None

    @property
    def altitude(self):
        proto_loc = self.get_parsed_location()
        if proto_loc is not None:
            return proto_loc.altitude
        return None

    @property
    def formatted_time(self):
        try:
            return datetime.datetime.fromtimestamp(self.time).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(self.time)

    @property
    def google_maps_link(self):
        lat, lon = self.latitude, self.longitude
        if lat is not None and lon is not None:
            return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
        return None

    def __str__(self):
        lines = ["WrappedLocation("]
        lines.append(f"  Time: {self.formatted_time} (timestamp={self.time})")
        lines.append(f"  Status: {self.status}")
        lines.append(f"  Accuracy: {self.accuracy}")
        lines.append(f"  Is Own Report: {self.is_own_report}")
        if self.name:
            lines.append(f"  Semantic Name: {self.name}")

        lat = self.latitude
        lon = self.longitude
        alt = self.altitude
        if lat is not None and lon is not None:
            lines.append(f"  Latitude: {lat}")
            lines.append(f"  Longitude: {lon}")
            if alt is not None:
                lines.append(f"  Altitude: {alt}")
            lines.append(f"  Google Maps Link: {self.google_maps_link}")

        if self.decrypted_location:
            lines.append(f"  Decrypted Bytes: {self.decrypted_location!r}")
        else:
            lines.append("  Decrypted Bytes: None")

        lines.append(")")
        return "\n".join(lines)

    def __repr__(self):
        return self.__str__()
