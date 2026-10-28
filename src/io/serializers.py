"""Reusable native storage backends, independent of application names."""

from __future__ import annotations

from zju_scatt_interface.extensions.native import native_model


def serialize_hdf5(path, arrays, template):
    import h5py

    def attrs(obj, values):
        for key, value in values.items():
            encoder = native_model(template["model"]).attribute
            if encoder is not None:
                value = encoder(key, value)
            obj.attrs[key] = value

    with h5py.File(path, "w") as handle:
        attrs(handle, template.get("attributes", {}))
        for name, attributes in template.get("groups", {}).items():
            attrs(handle.require_group(name), attributes)
        for name, value in arrays.items():
            attributes = template["variables"][name].get("attributes", {})
            options = {"compression": "gzip"} if "COMPRESSED" in attributes and value.size else {}
            level = template["variables"][name].get("compression", 0)
            if level and value.ndim and value.size:
                options = {"compression": "gzip", "compression_opts": level}
            obj = handle.create_dataset(name, data=value, **options)
            attrs(obj, template["variables"][name].get("attributes", {}))


def serialize_netcdf(path, arrays, template):
    fmt = template["format"]
    from netCDF4 import Dataset

    with Dataset(path, "w", format="NETCDF3_CLASSIC" if fmt == "netcdf3" else "NETCDF4") as handle:
        handle.setncatts(template.get("attributes", {}))
        for name, size in template["dimensions"].items():
            if size <= 0:
                raise ValueError("fixed NetCDF dimensions must be positive")
            handle.createDimension(name, size)
        containers = {"": handle}

        def container(path):
            if path not in containers:
                if fmt == "netcdf3":
                    raise ValueError("NetCDF3 does not support groups")
                (parent, _, leaf) = path.rpartition("/")
                containers[path] = container(parent).createGroup(leaf)
            return containers[path]

        for name, attributes in template.get("groups", {}).items():
            container(name).setncatts(attributes)
        for name, dimensions in template.get("group_dimensions", {}).items():
            for dimension, size in dimensions.items():
                if size <= 0:
                    raise ValueError("fixed NetCDF dimensions must be positive")
                container(name).createDimension(dimension, size)
        for name, value in arrays.items():
            spec = template["variables"][name]
            attrs = dict(spec.get("attributes", {}))
            fill = attrs.pop("_FillValue", None)
            (parent, _, leaf) = name.rpartition("/")
            options = {}
            if fmt == "netcdf4" and spec.get("compression", 0) and value.ndim and value.size:
                options = {"zlib": True, "complevel": spec["compression"]}
            var = container(parent).createVariable(
                leaf, value.dtype, spec["dimensions"], fill_value=fill, **options
            )
            var.setncatts(attrs)
            var[:] = value
