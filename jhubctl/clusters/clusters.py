import pprint
from traitlets.config import Configurable
from . import providers

from jhubctl.utils import kubectl, helm


class ClusterList(Configurable):
    """Class for managing a Kubernetes Clusters.

    This class manages your configuration for kubectl.
    """
    def __init__(self, kubeconf=None, **traits):
        self.kubeconf = kubeconf
        super().__init__(**traits)

    def get(self, name=None, provider='AwsEKS', print_output=True):
        """List all cluster.
        """
        # Create cluster object
        Cluster = getattr(providers, provider)
        cluster = Cluster(name)

        self.kubeconf.open()
        if name is None:
            clusters = self.kubeconf.get_clusters()
            print("Clusters:")
            for cluster in clusters:
                print(f"  - {cluster['name']}")
        else:
            cluster = self.kubeconf.get_cluster(name=cluster.cluster_name)
            pprint.pprint(cluster, depth=4)

    def create(self, name, provider='AwsEKS'):
        """Create a Kubernetes cluster on a given provider.
        """
        # ----- Create K8s cluster on provider -------
        # Create cluster object
        Cluster = getattr(providers, provider)
        cluster = Cluster(name)
        cluster.create()

        # -------- Add cluster to kubeconf -----------

        # Add cluster to kubeconf
        self.kubeconf.open()
        self.kubeconf.add_cluster(
            cluster.cluster_name,
            server=cluster.endpoint_url,
            certificate_authority_data=cluster.ca_cert
        )

        # Add a user to kubeconf
        self.kubeconf.add_user(name)

        # Add a user exec call for this provider.
        self.kubeconf.add_to_user(
            name,
            **cluster.kube_user_data
        )

        # Add context mapping user to cluster.
        self.kubeconf.add_context(
            name,
            cluster_name=cluster.cluster_name,
            user_name=cluster.name
        )

        # Switch contexts.
        self.kubeconf.set_current_context(name)

        # Commit changes to file.
        self.kubeconf.close()
        
        # ------ Setup autorization -------
        kubectl('apply', config_yaml=cluster.get_auth_config())

        # -------- Setup Storage ----------

        kubectl('apply', config_yaml=cluster.get_storage_config())

        # ------- setup helm locally ------
        kubectl(
            '--namespace',
            'kube-system',
            'create',
            'serviceaccount',
            'tiller'
        ).decode('utf-8')

        kubectl(
            'create',
            'clusterrolebinding',
            'tiller',
            'cluster-admin',
            '--serviceaccount=kube-system:tiller'
        ).decode('utf-8')

        # -------- Initialize Helm -----------
        helm(
            'init',
            '--service-account',
            'tiller'
        ).decode('utf-8')

        # --------- Secure Helm --------------
        kubectl(
            'patch',
            'deployment',
            'tiller-deploy',
            namespace='kube-system',
            type='json',
            patch='[{"op": "add", "path": "/spec/template/spec/containers/0/command", "value": ["/tiller", "--listen=localhost:44134"]}]'
        ).decode('utf-8')

    def delete(self, name, provider='AwsEKS'):
        """Delete a Kubernetes cluster.
        """
        # Create cluster object
        Cluster = getattr(providers, provider)
        cluster = Cluster(name)
        cluster.delete()

        # Remove from kubeconf
        self.kubeconf.open()
        self.kubeconf.remove_context(name)
        self.kubeconf.remove_user(name)
        self.kubeconf.remove_cluster(cluster.cluster_name)
        self.kubeconf.close()