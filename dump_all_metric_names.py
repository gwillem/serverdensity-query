import sdapi


def print_metrics(metrics, parents=None):
    # recursive

    parents = parents or []

    for i in metrics:
        path = '.'.join(parents + [i.get('key', 'unknown_key')])
        print("%s %s (%s)"
              % (path,
                 i.get('name'),
                 i.get('unit')
                 )
              )
        # parents.append(i.get('key', 'unknown_key'))
        if 'tree' in i:
            new_parents = parents + [i.get('key', 'anonymous_key')]
            print_metrics(i['tree'], parents=new_parents)

app_name = 'willem'
id = sdapi.device_name_to_id(app_name)
metrics = sdapi.all_metrics_for_device_id(id)
print_metrics(metrics)
