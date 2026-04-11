"""
Generate static GeoJSON files for FloodWatch Nigeria map layers.
Output: frontend/public/maps/*.geojson
Run from project root: python3 execution/gen_geojson.py
"""
import json, pathlib

BASE = pathlib.Path("frontend/public/maps")
BASE.mkdir(parents=True, exist_ok=True)

def box(lng, lat, d=0.12):
    """Simple polygon box ±d around centroid."""
    return [[[lng-d,lat-d],[lng+d,lat-d],[lng+d,lat+d],[lng-d,lat+d],[lng-d,lat-d]]]

STATES = {
    1:"Abia",2:"Adamawa",3:"Akwa Ibom",4:"Anambra",5:"Bauchi",6:"Bayelsa",
    7:"Benue",8:"Borno",9:"Cross River",10:"Delta",11:"Ebonyi",12:"Edo",
    13:"Ekiti",14:"Enugu",15:"Gombe",16:"Imo",17:"Jigawa",18:"Kaduna",
    19:"Kano",20:"Katsina",21:"Kebbi",22:"Kogi",23:"Kwara",24:"Lagos",
    25:"Nasarawa",26:"Niger",27:"Ogun",28:"Ondo",29:"Osun",30:"Oyo",
    31:"Plateau",32:"Rivers",33:"Sokoto",34:"Taraba",35:"Yobe",36:"Zamfara",
    37:"FCT Abuja"
}

LGAS = [
    ("Lokoja",22,"HIGH",6.74,7.80),("Ajaokuta",22,"HIGH",6.66,7.56),
    ("Ibaji",22,"HIGH",6.79,7.10),("Igalamela-Odolu",22,"HIGH",6.84,7.00),
    ("Idah",22,"HIGH",6.74,7.11),("Bassa",22,"MODERATE",6.68,8.17),
    ("Anambra East",4,"HIGH",6.84,6.30),("Anambra West",4,"HIGH",6.71,6.25),
    ("Ogbaru",4,"HIGH",6.76,5.95),("Onitsha South",4,"HIGH",6.79,6.14),
    ("Onitsha North",4,"HIGH",6.78,6.17),("Awka South",4,"MODERATE",7.07,6.21),
    ("Oshimili South",10,"HIGH",6.19,6.04),("Oshimili North",10,"HIGH",6.33,6.14),
    ("Ndokwa East",10,"HIGH",6.46,5.68),("Ndokwa West",10,"HIGH",6.26,5.65),
    ("Ukwuani",10,"HIGH",6.21,5.76),("Warri South",10,"HIGH",5.75,5.52),
    ("Warri North",10,"HIGH",5.56,5.72),("Burutu",10,"HIGH",5.51,5.35),
    ("Yenagoa",6,"HIGH",6.27,4.92),("Kolokuma-Opokuma",6,"HIGH",6.09,5.11),
    ("Ogbia",6,"HIGH",6.48,4.78),("Brass",6,"HIGH",6.23,4.31),
    ("Southern Ijaw",6,"HIGH",5.82,4.64),
    ("Port Harcourt",32,"HIGH",7.01,4.85),("Degema",32,"HIGH",6.77,4.73),
    ("Asari-Toru",32,"HIGH",6.87,4.61),
    ("Makurdi",7,"HIGH",8.54,7.73),("Agatu",7,"HIGH",7.87,7.72),
    ("Guma",7,"HIGH",8.34,7.83),("Logo",7,"HIGH",9.06,7.71),
    ("Gwer East",7,"HIGH",8.77,7.49),("Katsina-Ala",7,"HIGH",9.29,6.99),
    ("Kwande",7,"HIGH",9.30,7.07),
    ("Borgu",26,"HIGH",4.23,10.64),("Agaie",26,"HIGH",6.11,8.97),
    ("Lavun",26,"HIGH",5.60,9.02),("Edati",26,"MODERATE",5.90,9.37),
    ("Birnin Kebbi",21,"HIGH",4.20,12.45),("Argungu",21,"HIGH",4.52,12.74),
    ("Ngaski",21,"HIGH",4.55,11.41),("Yauri",21,"HIGH",4.43,11.44),
    ("Bagudo",21,"HIGH",4.37,11.80),
    ("Sokoto North",33,"MODERATE",5.23,13.06),("Bodinga",33,"HIGH",4.89,12.97),
    ("Dange Shuni",33,"HIGH",5.33,12.86),
    ("Hadejia",17,"HIGH",10.04,12.46),("Kafin Hausa",17,"HIGH",9.32,12.59),
    ("Guri",17,"HIGH",10.48,12.72),
    ("Maiduguri",8,"HIGH",13.16,11.83),("Konduga",8,"HIGH",13.40,11.69),
    ("Jere",8,"HIGH",13.14,11.90),("Nganzai",8,"HIGH",13.55,12.68),
    ("Mobbar",8,"HIGH",13.24,13.35),
    ("Geidam",35,"HIGH",11.93,12.89),("Bade",35,"HIGH",10.92,12.82),
    ("Calabar South",9,"HIGH",8.33,4.96),("Akpabuyo",9,"HIGH",8.41,4.85),
    ("Bakassi",9,"HIGH",8.69,4.61),
    ("Wukari",34,"HIGH",9.78,7.87),("Donga",34,"HIGH",10.03,7.60),
    ("Fufore",2,"HIGH",12.78,9.36),("Demsa",2,"HIGH",12.14,9.08),
    ("Shendam",31,"HIGH",9.53,8.88),("Wase",31,"HIGH",10.00,9.10),
    ("Edu",23,"HIGH",5.16,9.10),("Kaiama",23,"HIGH",3.94,9.58),
    ("Awe",25,"HIGH",8.22,8.38),("Obi",25,"HIGH",8.74,8.52),
    ("Ilaje",28,"HIGH",5.08,6.48),("Ese-Odo",28,"HIGH",5.65,6.14),
    ("Etsako West",12,"HIGH",6.30,7.01),("Orhionmwon",12,"HIGH",5.75,6.38),
    ("Oguta",16,"HIGH",6.78,5.70),("Ohaji-Egbema",16,"HIGH",6.84,5.47),
    ("Osisioma",1,"HIGH",7.37,5.51),("Ugwunagbo",1,"HIGH",7.52,5.23),
    ("Epe",24,"HIGH",3.98,6.59),("Ikorodu",24,"HIGH",3.51,6.62),
    ("Lagos Island",24,"HIGH",3.38,6.45),("Ikeja",24,"MODERATE",3.34,6.60),
    ("Oshodi-Isolo",24,"MODERATE",3.29,6.54),
    ("Abeokuta South",27,"MODERATE",3.35,7.16),
    ("Sagamu",27,"MODERATE",3.66,6.84),
    ("Ibadan South-West",30,"LOW",3.90,7.37),
    ("Ogbomosho North",30,"LOW",4.24,8.13),
    ("Akure South",28,"LOW",5.20,7.25),
    ("Enugu North",14,"LOW",7.49,6.46),
    ("Abakaliki",11,"MODERATE",8.11,6.32),
    ("Umuahia North",1,"LOW",7.49,5.53),
    ("Owerri Municipal",16,"LOW",7.03,5.48),
    ("Uyo",3,"MODERATE",7.85,5.01),
    ("Eket",3,"HIGH",7.92,4.65),
    ("Calabar Municipality",9,"MODERATE",8.33,4.97),
    ("Zaria",18,"LOW",7.72,11.07),
    ("Kaduna North",18,"LOW",7.44,10.52),
    ("Kano Municipal",19,"LOW",8.53,12.00),
    ("Faskari",20,"MODERATE",7.33,12.51),
    ("Dutse",17,"LOW",9.34,11.77),
    ("Jos North",31,"LOW",8.90,9.92),
    ("Lafia",25,"LOW",8.52,8.49),
    ("Minna",26,"LOW",6.56,9.61),
    ("Gwagwalada",37,"LOW",7.10,8.95),
    ("Abuja Municipal",37,"LOW",7.49,9.06),
]

features = []
for (name, sid, risk, lng, lat) in LGAS:
    features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": box(lng, lat)},
        "properties": {
            "name_en": name,
            "state_name": STATES[sid],
            "flood_risk_class": risk
        }
    })

import time
fc = {"type":"FeatureCollection","_cached_at_ms":int(time.time()*1000),"features":features}
path = BASE / "lga-flood-risk.geojson"
path.write_text(json.dumps(fc, separators=(',',':')))
print(f"  OK  {path} ({len(features)} LGAs)")

# ---- afo-communities.geojson ----
AFO = [
    ("Lokoja City","HIGHLY_PROBABLE",6.74,7.80),
    ("Onitsha Waterfront","HIGHLY_PROBABLE",6.79,6.14),
    ("Yenagoa Central","HIGHLY_PROBABLE",6.27,4.92),
    ("Port Harcourt East","HIGHLY_PROBABLE",7.01,4.85),
    ("Makurdi Town","HIGHLY_PROBABLE",8.54,7.73),
    ("Warri Riverside","HIGHLY_PROBABLE",5.75,5.52),
    ("Katsina-Ala Town","HIGHLY_PROBABLE",9.29,6.99),
    ("Maiduguri Konduga","HIGHLY_PROBABLE",13.35,11.74),
    ("Laggo Dam Downstream","HIGHLY_PROBABLE",13.29,11.88),
    ("Idah Riverside","HIGHLY_PROBABLE",6.74,7.11),
    ("Wukari Town","HIGHLY_PROBABLE",9.78,7.87),
    ("Argungu Town","HIGHLY_PROBABLE",4.52,12.74),
    ("Hadejia Town","PROBABLE",10.04,12.46),
    ("Ibaji Community","PROBABLE",6.79,7.10),
    ("Brass Oil Area","PROBABLE",6.23,4.31),
    ("Bakassi Peninsula","PROBABLE",8.69,4.61),
    ("Etsako West","PROBABLE",6.30,7.01),
    ("Ilaje Coastal","PROBABLE",5.08,6.48),
    ("Epe Lagoon","PROBABLE",3.98,6.59),
    ("Ikorodu North","PROBABLE",3.51,6.62),
    ("Borgu Riverside","PROBABLE",4.23,10.64),
    ("Ngaski Kebbi","PROBABLE",4.55,11.41),
    ("Geidam Town","PROBABLE",11.93,12.89),
    ("Demsa Town","PROBABLE",12.14,9.08),
    ("Calabar South","PROBABLE",8.33,4.96),
    ("Shendam Valley","PROBABLE",9.53,8.88),
    ("Edu Kwara","PROBABLE",5.16,9.10),
    ("Kaiama Town","PROBABLE",3.94,9.58),
    ("Lagos Island","LOW_RISK",3.38,6.45),
    ("Abeokuta South","LOW_RISK",3.35,7.16),
    ("Minna Town","LOW_RISK",6.56,9.61),
    ("Lafia Town","LOW_RISK",8.52,8.49),
    ("Jos North","LOW_RISK",8.90,9.92),
]
afo_features = [{
    "type":"Feature",
    "geometry":{"type":"Point","coordinates":[lng,lat]},
    "properties":{"community":name,"afo_class":cls}
} for (name,cls,lng,lat) in AFO]
afo_fc = {"type":"FeatureCollection","features":afo_features}
path2 = BASE / "afo-communities.geojson"
path2.write_text(json.dumps(afo_fc, separators=(',',':')))
print(f"  OK  {path2} ({len(afo_features)} communities)")

# ---- shelter-locations.geojson ----
SHELTERS = [
    ("NEMA IDP Camp Maiduguri",13.17,11.84,3000,"Maiduguri Stadium, Borno","OPEN"),
    ("NEMA Shelter Lokoja",6.74,7.80,1500,"Government Primary School, Kogi","OPEN"),
    ("NEMA Shelter Port Harcourt",7.01,4.86,2000,"Rivers State University Annex","OPEN"),
    ("NEMA Shelter Makurdi",8.54,7.73,1200,"Benue State University Campus","OPEN"),
    ("Red Cross Shelter Yenagoa",6.27,4.92,800,"NYSC Permanent Orientation Camp","OPEN"),
    ("NEMA Shelter Onitsha",6.79,6.14,1800,"Onitsha Central School","OPEN"),
    ("NEMA Shelter Warri",5.75,5.52,1000,"PTI Conference Center","OPEN"),
    ("NEMA Shelter Lagos Mainland",3.38,6.46,2500,"Lagos State Secretariat Annex","OPEN"),
    ("NEMA Shelter Ikorodu",3.51,6.62,1000,"Ikorodu Community Hall","OPEN"),
    ("NEMA Shelter Abeokuta",3.35,7.16,800,"Ogun State Secretariat","OPEN"),
    ("NEMA Shelter Kano",8.53,12.00,2000,"Kano State Emergency Centre","OPEN"),
    ("NEMA Shelter Kaduna",7.44,10.52,1500,"Kaduna State Stadium","OPEN"),
    ("NEMA Shelter Sokoto",5.23,13.06,1000,"Sokoto Central School","OPEN"),
    ("NEMA Shelter Birnin Kebbi",4.20,12.45,800,"Kebbi State School","OPEN"),
    ("NEMA Shelter Calabar",8.33,4.96,1200,"Calabar Municipal Hall","OPEN"),
    ("NEMA Shelter Wukari",9.78,7.87,600,"Wukari LGA Hall","OPEN"),
    ("NEMA Shelter Hadejia",10.04,12.46,700,"Hadejia Local School","OPEN"),
    ("NEMA Shelter Yola",12.43,9.26,1000,"Adamawa State Emergency Hall","OPEN"),
    ("NEMA Shelter Jos",8.90,9.92,1500,"Plateau State Stadium","OPEN"),
    ("NEMA Shelter Abuja",7.49,9.06,3000,"NEMA HQ Emergency Hall, FCT","OPEN"),
    ("Red Cross Shelter Akure",5.20,7.25,800,"Ondo State School","OPEN"),
    ("NEMA Shelter Owerri",7.03,5.48,1000,"Imo State Sports Complex","OPEN"),
    ("NEMA Shelter Uyo",7.85,5.01,1200,"Akwa Ibom State School","OPEN"),
    ("NEMA Shelter Ibadan",3.90,7.38,2000,"Oyo State Secretariat","OPEN"),
    ("NEMA Shelter Benin City",5.62,6.34,1500,"Edo State School","OPEN"),
    ("NEMA Shelter Enugu",7.49,6.46,1200,"Enugu State School","OPEN"),
    ("NEMA Shelter Asaba",6.78,6.12,1000,"Delta State School","OPEN"),
    ("NEMA Shelter Lafia",8.52,8.49,800,"Nasarawa State Hall","OPEN"),
    ("NEMA Shelter Minna",6.56,9.61,1000,"Niger State School","OPEN"),
    ("NEMA Shelter Ilorin",4.58,8.50,1500,"Kwara State Emergency Centre","OPEN"),
]
shelter_features = [{
    "type":"Feature",
    "geometry":{"type":"Point","coordinates":[lng,lat]},
    "properties":{"name":name,"capacity":cap,"address":addr,"status":status}
} for (name,lng,lat,cap,addr,status) in SHELTERS]
shelter_fc = {"type":"FeatureCollection","features":shelter_features}
path3 = BASE / "shelter-locations.geojson"
path3.write_text(json.dumps(shelter_fc, separators=(',',':')))
print(f"  OK  {path3} ({len(shelter_features)} shelters)")
print("Done.")
