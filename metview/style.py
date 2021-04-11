#
# (C) Copyright 2017- ECMWF.
#
# This software is licensed under the terms of the Apache Licence Version 2.0
# which can be obtained at http://www.apache.org/licenses/LICENSE-2.0.
#
# In applying this licence, ECMWF does not waive the privileges and immunities
# granted to it by virtue of its status as an intergovernmental organisation
# nor does it submit to any jurisdiction.
#

import copy
import logging
import os

import yaml
import metview as mv

# logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger(__name__)

_DB = {
    "param": (None, "params.yaml", "param_style.yaml"),
    "map": (None, "", "map_style.yaml"),
}

ETC_PATH = os.path.join(os.path.dirname(__file__), "etc")
CUSTOM_CONF_PATH = ""
LOCAL_CONF_PATH = ""

# def get_db(name="param"):
#     global _DB
#     assert name in _DB
#     if _DB[name][0] is None:
#         _DB[name] = (StyleDb(_DB[name][1]), "")
#     return _DB[name][0]

PARAM_VISDEF_VERBS = ["mcont", "mwind", "mcoast", "msymb", "mgraph"]


class Visdef:
    # BUILDER = {
    #     "mcont": mv.mcont,
    #     "mwind": mv.mwind,
    #     "mcoast": mv.mcoast,
    #     "msymb": mv.msymb,
    #     "mgraph": mv.mgraph
    # }

    def __init__(self, verb, params):
        self.verb = verb
        self.params = params

        self.BUILDER = {
            "mcont": mv.mcont,
            "mwind": mv.mwind,
            "mcoast": mv.mcoast,
            "msymb": mv.msymb,
            "mgraph": mv.mgraph,
        }

    def clone(self):
        return Visdef(self.verb, copy.deepcopy(self.params))

    def change(self, verb, param, value):
        if verb == self.verb:
            self.params[param] = value

    def change_symbol_text_list(self, value):
        assert self.verb == "msymb"
        if self.verb == "msymb":
            if self.params.get("symbol_type", "").lower() == "text":
                self.params["symbol_text_list"] = value

    def to_request(self):
        fn = self.BUILDER.get(self.verb, None)
        if fn is not None:
            return fn(**(self.params))
        else:
            raise Exception(f"{self} unsupported verb!")

    def __str__(self):
        return f"Visdef[verb={self.verb}, params={self.params}]"

    def __repr__(self):
        return f"Visdef(verb={self.verb}, params={self.params})"


class Style:
    def __init__(self, name, visdefs):
        self.name = name
        self.visdefs = visdefs

    def clone(self):
        return Style(self.name, [vd.clone() for vd in self.visdefs])

    def to_request(self):
        return [vd.to_request() for vd in self.visdefs]

    def update(self, *args, inplace=None):
        s = self if inplace == True else self.clone()
        for i, v in enumerate(args):
            if i < len(s.visdefs):
                if isinstance(v, dict):
                    v = {v_key.lower(): v_val for v_key, v_val in v.items()}
                    s.visdefs[i].params.update(v)
        return s

    def __str__(self):
        t = f"{self.__class__.__name__}[name={self.name}] "
        for vd in self.visdefs:
            t += f"{vd} "
        return t


class ParamMatchCondition:
    def __init__(self, cond):
        self.cond = cond
        if "levels" in self.cond:
            if not isinstance(self.cond["levels"], list):
                self.cond["levels"] = [self.cond["levels"]]

    def match(self, param):
        return param.match(
            self.cond.get("info_name", ""),
            self.cond.get("level_type", None),
            self.cond.get("levels", []),
        )


class ParamStyle:
    def __init__(self, conf, db):
        self.cond = []
        for d in conf["match"]:
            self.cond.append(ParamMatchCondition(d))
            if "info_name" in d:
                self.info_name = d["info_name"]
        self.param_type = conf.get("param_type", "scalar")

        if self.param_type == "vector":
            default_style = db.VECTOR_DEFAULT_STYLE_NAME
        else:
            default_style = db.SCALAR_DEFAULT_STYLE_NAME

        self.style = conf.get("styles", [default_style])
        self.xs_style = conf.get("xs_styles", self.style)
        self.diff_style = conf.get("diff_styles", [db.DIFF_DEFAULT_STYLE_NAME])

    def match(self, param):
        return max([d.match(param) for d in self.cond])

    def find_style(self, plot_type):
        if plot_type == "" or plot_type == "map":
            return self.style[0]
        elif plot_type == "diff":
            return self.diff_style[0]
        elif plot_type == "xs":
            return self.xs_style[0]
        else:
            return None

    def __str__(self):
        return "{}[param={},style={}] groups={}".format(
            self.__class__.__name__,
            self.param_name,
            self.style.name,
            [gr.__str__() for gr in self.groups],
        )


class StyleDb:
    SCALAR_DEFAULT_STYLE_NAME = "default_mcont"
    VECTOR_DEFAULT_STYLE_NAME = "default_mwind"
    DIFF_DEFAULT_STYLE_NAME = "default_diff"

    def __init__(self, param_file_name, style_file_name):
        self.params = []
        self.styles = {}

        if LOCAL_CONF_PATH:
            self._load(
                os.path.join(LOCAL_CONF_PATH, param_file_name) if param_file_name else "",
                os.path.join(LOCAL_CONF_PATH, style_file_name),
            )

        if CUSTOM_CONF_PATH:
            self._load(
                os.path.join(CUSTOM_CONF_PATH, param_file_name) if param_file_name else "",
                os.path.join(CUSTOM_CONF_PATH, style_file_name),
            )

        # load system defs
        self._load(
            os.path.join(ETC_PATH, param_file_name) if param_file_name else "",
            os.path.join(ETC_PATH, style_file_name),
        )

        # LOG.debug(f"custom_conf_path={CUSTOM_CONF_PATH}")

    @staticmethod
    def get_db(name="param"):
        global _DB
        assert name in _DB
        if _DB[name][0] is None:
            _DB[name] = (StyleDb(_DB[name][1], _DB[name][2]), "")
        return _DB[name][0]

    def get_style(self, style):
        if style in self.styles:
            return self.styles[style]
        else:
            return self.styles.get("default", None)

    def get_param_style(self, param, scalar=True, plot_type="map"):
        r = 0
        p_best = None
        for p in self.params:
            m = p.match(param)
            # print(f"m={m}")
            if m > r:
                r = m
                p_best = p

        print(f"param={param}")
        if p_best is not None:
            s = p_best.find_style(plot_type)
            print(f" -> style={s}")
            return self.styles.get(s, None)
        else:
            if scalar:
                return self.styles.get(self.SCALAR_DEFAULT_STYLE_NAME, None)
            else:
                return self.styles.get(self.VECTOR_DEFAULT_STYLE_NAME, None)

        return None

    def style(self, fs, plot_type="map"):
        param = fs.param_info
        if param is not None:
            vd = self.get_param_style(param, scalar=param.scalar, plot_type=plot_type)
            # LOG.debug(f"vd={vd}")
            return vd
        return None

    def visdef(self, fs, plot_type="map"):
        vd = self.style(fs, plot_type=plot_type)
        return vd.to_request() if vd is not None else None

    @staticmethod
    def set_config(conf_dir):
        global CUSTOM_CONF_PATH
        CUSTOM_CONF_PATH = conf_dir

    def _make_defaults(self):
        d = {
            self.SCALAR_DEFAULT_STYLE_NAME: "mcont",
            self.VECTOR_DEFAULT_STYLE_NAME: "mwind",
            self.DIFF_DEFAULT_STYLE_NAME: "mcont",
        }
        for name, verb in d.items():
            if name not in self.styles:
                self.styles[name] = Style(name, Visdef(verb, {}))
        assert self.SCALAR_DEFAULT_STYLE_NAME in self.styles
        assert self.VECTOR_DEFAULT_STYLE_NAME in self.styles
        assert self.DIFF_DEFAULT_STYLE_NAME in self.styles

    def _load(self, param_path, style_path):
        if os.path.exists(style_path):
            with open(style_path, "rt") as f:
                c = yaml.safe_load(f)
                self._load_styles(c)
            if os.path.exists(param_path):
                with open(param_path, "rt") as f:
                    c = yaml.safe_load(f)
                    self._load_params(c, param_path)

    def _load_styles(self, conf):
        for name, d in conf.items():
            vd = []
            # print(f"name={name} d={d}")
            if not isinstance(d, list):
                d = [d]

            # print(f"name={name} d={d}")
            # for mcoast the verb can be missing
            if (
                len(d) == 1
                and isinstance(d[0], dict)
                and (len(d[0]) > 1 or not list(d[0].keys())[0] in PARAM_VISDEF_VERBS)
            ):
                vd.append(Visdef("mcoast", d[0]))
            else:
                for v in d:
                    ((verb, params),) = v.items()
                    vd.append(Visdef(verb, params))
            self.styles[name] = Style(name, vd)

        # if self.system:
        self._make_defaults()

    def _load_params(self, conf, path):
        for d in conf:
            assert isinstance(d, dict)
            # print(f"d={d}")
            p = ParamStyle(d, self)
            for v in [p.style, p.xs_style, p.diff_style]:
                # print(f"v={v}")
                for s in v:
                    if not s in self.styles:
                        raise Exception(
                            f"{self} Invalid style={s} specified in {d}! File={path}"
                        )

            self.params.append(p)

    def is_empty(self):
        return len(self.styles) == 0

    def __str__(self):
        return self.__class__.__name__

    def print(self):
        pass
        # print(f"{self} params=")
        # for k, v in self.params.items():
        #     print(v)
        # print(f"{self} styles=")
        # for k, v in self.styles.items():
        #     print(v)


class GeoView:
    def __init__(self, params, style):
        self.params = copy.deepcopy(params)
        for k in list(self.params.keys()):
            if k.lower() == "coastlines":
                self.params.pop("coastlines", None)
        self.style = style
        if self.style is None:
            assert self.style.verb == "mcoast"

    def to_request(self):
        v = copy.deepcopy(self.params)
        if self.style is not None and self.style:
            v["coastlines"] = self.style.to_request()
        return mv.geoview(**v)

    def __str__(self):
        t = f"{self.__class__.__name__}[params={self.params}, style={self.style}]"
        return t


class MapConf:
    items = []
    areas = []
    BUILTIN_AREAS = [
        "ANTARCTIC",
        "ARCTIC",
        "AUSTRALASIA",
        "CENTRAL_AMERICA",
        "CENTRAL_EUROPE",
        "EAST_TROPIC",
        "EASTERN_ASIA",
        "EQUATORIAL_PACIFIC",
        "EURASIA",
        "EUROPE",
        "GLOBAL",
        "MIDDLE_EAST_AND_INDIA",
        "NORTH_AMERICA",
        "NORTH_ATLANTIC",
        "NORTH_EAST_EUROPE",
        "NORTH_POLE",
        "NORTH_WEST_EUROPE",
        "NORTHERN_AFRICA",
        "PACIFIC",
        "SOUTH_AMERICA",
        "SOUTH_ATLANTIC_AND_INDIAN_OCEAN",
        "SOUTH_EAST_ASIA_AND_INDONESIA",
        "SOUTH_EAST_EUROPE",
        "SOUTH_POLE",
        "SOUTH_WEST_EUROPE",
        "SOUTHERN_AFRICA",
        "SOUTHERN_ASIA",
        "WEST_TROPIC",
        "WESTERN_ASIA",
    ]

    def __init__(self):
        self.areas = {}
        self.style_db = StyleDb.get_db(name="map")

        # load areas
        self._load_areas(os.path.join(ETC_PATH, "areas.yaml"))
        if CUSTOM_CONF_PATH:
            self._load_areas(os.path.join(CUSTOM_CONF_PATH, "areas.yaml"))
        if LOCAL_CONF_PATH:
            self._load_areas(os.path.join(LOCAL_CONF_PATH, "areas.yaml"))

    def _load_areas(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, "rt") as f:
                # the file can be empty!
                d = yaml.safe_load(f)
                if isinstance(d, list):
                    for item in d:
                        ((name, conf),) = item.items()
                        self.areas[name] = conf

    def find(self, area=None, style=None):
        area_v = "base" if area is None else area
        style_v = "grey_light_base" if style is None else style
        a = self.areas.get(area_v, {})
        s = None
        if len(a) == 0 and area_v.upper() in self.BUILTIN_AREAS:
            a = {"area_mode": "name", "area_name": area}
        # if a is not None:
        s = self.style_db.get_style(style_v)
        return a, s

    def view(self, area=None, style=None, plot_type=None):
        a, s = self.find(area=area, style=style)
        # a["map_overlay_control"] = "by_date"

        if plot_type == "stamp":
            s = s.update({"map_grid": "off", "map_label": "off"})
        return GeoView(a, s)
        # if s is not None and s:
        #     a["coastlines"] = s.to_request()
        # # return mv.geoview(**a)
        # return a


if __name__ == "__main__":
    vd = StyleConf()
    vd.print()
else:
    pass
