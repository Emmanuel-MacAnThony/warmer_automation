import json

dev = json.load(open('data/samples/matthew_putman_dev_fusion.json', encoding='utf-8'))
hv  = json.load(open('data/samples/matthew_putman_harvestapi_profile.json', encoding='utf-8'))
dev_raw = dev.get('raw_data', {})

print('=== KEY FIELD COMPARISON ===\n')
checks = [
    ('full name',       dev_raw.get('fullName'),                                       f"{hv.get('firstName')} {hv.get('lastName')}"),
    ('headline',        dev_raw.get('headline'),                                       hv.get('headline')),
    ('location',        dev_raw.get('addressWithCountry'),                             hv.get('location')),
    ('followers',       dev_raw.get('followers'),                                      hv.get('followerCount')),
    ('connections',     dev_raw.get('connections'),                                    hv.get('connectionsCount')),
    ('about',           str(dev_raw.get('about') or '')[:60],                         str(hv.get('about') or '')[:60]),
    ('premium',         dev_raw.get('isPremium'),                                      hv.get('premium')),
    ('open to work',    dev_raw.get('isJobSeeker'),                                    hv.get('openToWork')),
    ('exp count',       dev_raw.get('experiencesCount'),                               len(hv.get('experience') or [])),
    ('total exp yrs',   dev_raw.get('totalExperienceYears'),                           'NOT IN harvestapi'),
    ('email',           dev_raw.get('email'),                                          hv.get('emails')),
    ('causes',          'NOT IN dev_fusion',                                           hv.get('causes')),
    ('currentPosition', dev_raw.get('companyName'),                                    str(hv.get('currentPosition') or '')[:60]),
]

for label, dv, hv_val in checks:
    print(f'  {label:<18}  dev={str(dv):<40}  harvest={hv_val}')

print('\n=== EXPERIENCE STRUCTURE (first role) ===')
dev_exp = (dev_raw.get('experiences') or [{}])[0]
hv_exp  = (hv.get('experience') or [{}])[0]
print('dev_fusion keys:', list(dev_exp.keys()))
print('harvestapi keys:', list(hv_exp.keys()))
print()
print('dev company:    ', dev_exp.get('companyName'))
print('hv  company:    ', hv_exp.get('companyName') or hv_exp.get('company'))
print('dev title:      ', dev_exp.get('title'))
print('hv  title:      ', hv_exp.get('title'))
print('dev start:      ', dev_exp.get('jobStartedOn'))
print('hv  start:      ', hv_exp.get('startedOn') or hv_exp.get('jobStartedOn'))
print('dev industry:   ', dev_exp.get('companyIndustry'))
print('hv  industry:   ', hv_exp.get('companyIndustry') or hv_exp.get('industry'))
